"""Calendar Agent for ZERO (Milestone M13).

Provides calendar event management, scheduling, conflict detection, and meeting prep.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class CalendarEvent:
    """Represents a calendar event or meeting."""
    event_id: str
    title: str
    start_time: str  # ISO timestamp
    end_time: str    # ISO timestamp
    attendees: List[str] = field(default_factory=list)
    location: str = "Online / Google Meet"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CalendarAgent:
    """Native Calendar Agent managing schedules, meetings, and conflicts."""

    def __init__(self):
        self._events: Dict[str, CalendarEvent] = {}

    def add_event(self, event: CalendarEvent) -> None:
        self._events[event.event_id] = event

    def list_events(self) -> List[CalendarEvent]:
        # Return sorted by start_time
        return sorted(self._events.values(), key=lambda e: e.start_time)

    def summarize_schedule(self) -> str:
        """Returns a formatted summary of upcoming events from Google Calendar or local cache."""
        from zero_core.adapters.google_workspace import DEFAULT_CALENDAR_LIVE_ADAPTER

        if DEFAULT_CALENDAR_LIVE_ADAPTER.is_configured():
            live_events = DEFAULT_CALENDAR_LIVE_ADAPTER.get_upcoming_events(hours_ahead=24)
            if live_events:
                lines = [f"Calendar Agent (Live Google Calendar): {len(live_events)} upcoming event(s):"]
                for ev in live_events:
                    loc = f" ({ev.location})" if ev.location else ""
                    lines.append(f"  - [{ev.start_time} - {ev.end_time}] '{ev.summary}'{loc}")
                return "\n".join(lines)

        events = self.list_events()
        if not events:
            return "Calendar Agent: No upcoming meetings scheduled on your calendar."

        lines = [f"Calendar Agent: {len(events)} upcoming event(s):"]
        for ev in events:
            attendee_str = f" with {', '.join(ev.attendees)}" if ev.attendees else ""
            lines.append(f"  - [{ev.start_time} - {ev.end_time}] '{ev.title}'{attendee_str} ({ev.location})")
        return "\n".join(lines)

    def detect_conflicts(self, start_time: str, end_time: str) -> List[CalendarEvent]:
        """Detects overlapping events for a proposed time window."""
        conflicts = []
        try:
            req_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            req_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        except Exception:
            return []

        for ev in self._events.values():
            try:
                ev_start = datetime.fromisoformat(ev.start_time.replace("Z", "+00:00"))
                ev_end = datetime.fromisoformat(ev.end_time.replace("Z", "+00:00"))
                # Check interval overlap: max(start1, start2) < min(end1, end2)
                if max(req_start, ev_start) < min(req_end, ev_end):
                    conflicts.append(ev)
            except Exception:
                continue

        return conflicts

    def schedule_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        attendees: Optional[List[str]] = None,
        location: str = "Online",
        description: str = "",
    ) -> Dict[str, Any]:
        """Schedules a new event, checking for conflicts."""
        conflicts = self.detect_conflicts(start_time, end_time)
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        new_event = CalendarEvent(
            event_id=event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees or [],
            location=location,
            description=description,
        )
        self.add_event(new_event)
        return {
            "success": True,
            "event": new_event.to_dict(),
            "has_conflicts": len(conflicts) > 0,
            "conflicting_events": [c.to_dict() for c in conflicts],
        }

    def prepare_meeting_brief(self, event_id: str) -> str:
        """Generates a preparation brief for a scheduled meeting."""
        event = self._events.get(event_id)
        if event is None:
            return f"Event '{event_id}' not found in calendar."

        lines = [
            f"=== Meeting Brief: {event.title} ===",
            f"Time: {event.start_time} to {event.end_time}",
            f"Location: {event.location}",
            f"Attendees: {', '.join(event.attendees) if event.attendees else 'None specified'}",
        ]
        if event.description:
            lines.append(f"Agenda & Notes: {event.description}")
        return "\n".join(lines)


# Global singleton instance for ZERO runtime execution
DEFAULT_CALENDAR_AGENT = CalendarAgent()
