"""Google Workspace (Gmail & Calendar) domain tools for ZERO Tool Registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from zero_core.agents.calendar_agent import DEFAULT_CALENDAR_AGENT
from zero_core.agents.email_agent import DEFAULT_EMAIL_AGENT
from zero_core.tools.base import BaseTool, tool


class GetCalendarAgendaInput(BaseModel):
    hours_ahead: int = Field(default=24, description="Lookahead window in hours for upcoming meetings (1-168)")


class GetUnreadEmailsInput(BaseModel):
    max_results: int = Field(default=5, description="Maximum number of unread email highlights to retrieve (1-20)")


class CreateEmailDraftInput(BaseModel):
    recipient: str = Field(description="Email address of the recipient")
    subject: str = Field(description="Subject line of the email draft")
    body: str = Field(description="Body content of the email draft")
    reply_to_id: Optional[str] = Field(default=None, description="Optional ID of the message being replied to")


class ScheduleCalendarEventInput(BaseModel):
    title: str = Field(description="Meeting or event title")
    start_time: str = Field(description="Start time in ISO format (e.g. '2026-08-20T10:00:00Z')")
    end_time: str = Field(description="End time in ISO format (e.g. '2026-08-20T11:00:00Z')")
    attendees: Optional[List[str]] = Field(default=None, description="List of attendee email addresses")
    location: str = Field(default="Online", description="Event location or meeting link")
    description: str = Field(default="", description="Meeting notes or agenda")


class SendEmailInput(BaseModel):
    recipient: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body text")


@tool(
    name="workspace_calendar_agenda",
    description="Retrieves upcoming meetings, agendas, and scheduled calendar events.",
    args_model=GetCalendarAgendaInput,
    risk_level="read_only",
)
def workspace_calendar_agenda_tool(hours_ahead: int = 24) -> str:
    return DEFAULT_CALENDAR_AGENT.summarize_schedule()


@tool(
    name="workspace_unread_emails",
    description="Fetches recent unread inbox emails and highlights priority senders.",
    args_model=GetUnreadEmailsInput,
    risk_level="read_only",
)
def workspace_unread_emails_tool(max_results: int = 5) -> str:
    return DEFAULT_EMAIL_AGENT.summarize_inbox()


@tool(
    name="workspace_create_email_draft",
    description="Creates an email draft in the local draft queue.",
    args_model=CreateEmailDraftInput,
    risk_level="safe_write",
)
def workspace_create_email_draft_tool(
    recipient: str,
    subject: str,
    body: str,
    reply_to_id: Optional[str] = None,
) -> Dict[str, Any]:
    draft = DEFAULT_EMAIL_AGENT.create_draft(
        reply_to_id=reply_to_id,
        recipient=recipient,
        subject=subject,
        body=body,
    )
    return {
        "status": "draft_created",
        "draft": draft,
    }


@tool(
    name="workspace_schedule_event",
    description="Schedules a new calendar event and checks for scheduling conflicts.",
    args_model=ScheduleCalendarEventInput,
    risk_level="safe_write",
)
def workspace_schedule_event_tool(
    title: str,
    start_time: str,
    end_time: str,
    attendees: Optional[List[str]] = None,
    location: str = "Online",
    description: str = "",
) -> Dict[str, Any]:
    return DEFAULT_CALENDAR_AGENT.schedule_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        attendees=attendees,
        location=location,
        description=description,
    )


@tool(
    name="workspace_send_email",
    description="Sends an actual outgoing email message. HIGH RISK action requiring explicit approval.",
    args_model=SendEmailInput,
    risk_level="destructive",
)
def workspace_send_email_tool(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    res = DEFAULT_EMAIL_AGENT.send_email(recipient=recipient, subject=subject, body=body)
    return {
        "status": "sent" if res.get("success") else "failed",
        "recipient": recipient,
        "subject": subject,
        "bytes_sent": len(body),
        "details": res,
    }


WORKSPACE_TOOLS: List[BaseTool] = [
    workspace_calendar_agenda_tool,
    workspace_unread_emails_tool,
    workspace_create_email_draft_tool,
    workspace_schedule_event_tool,
    workspace_send_email_tool,
]
