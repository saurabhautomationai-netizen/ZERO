from __future__ import annotations

from zero_core.agents.email_agent import (
    DEFAULT_EMAIL_AGENT,
    EmailAgent,
    EmailMessage,
)
from zero_core.executors import execute
from zero_core.native_agents import EMAIL_AGENT


def test_email_agent_empty_inbox():
    agent = EmailAgent()
    summary = agent.summarize_inbox()
    assert "Inbox is clean" in summary


def test_email_agent_triage_and_summary():
    agent = EmailAgent()
    agent.add_message(
        EmailMessage(
            message_id="msg_1",
            sender="boss@example.com",
            recipient="me@example.com",
            subject="Urgent: Production Deployment Sign-off",
            snippet="Please review the release candidates.",
            body="Full details regarding the hotfix release.",
            labels=["urgent", "work"],
        )
    )
    agent.add_message(
        EmailMessage(
            message_id="msg_2",
            sender="newsletter@tech.io",
            recipient="me@example.com",
            subject="Weekly AI Digest",
            snippet="Top 10 breakthroughs in agentic systems.",
            body="Here is your weekly digest.",
            labels=["newsletter"],
        )
    )

    summary = agent.summarize_inbox()
    assert "2 unread email(s)" in summary
    assert "[URGENT]" in summary

    triaged = agent.triage_inbox()
    assert len(triaged["urgent"]) == 1
    assert len(triaged["newsletter"]) == 1
    assert triaged["urgent"][0]["message_id"] == "msg_1"


def test_email_agent_create_draft_and_search():
    agent = EmailAgent()
    agent.add_message(
        EmailMessage(
            message_id="msg_3",
            sender="client@corp.com",
            recipient="me@example.com",
            subject="Contract Renewal Inquiry",
            snippet="Checking on terms for next quarter.",
            body="Can we schedule a call to review the SLA?",
        )
    )

    results = agent.search("contract")
    assert len(results) == 1
    assert results[0].message_id == "msg_3"

    draft = agent.create_draft(
        reply_to_id="msg_3",
        recipient="client@corp.com",
        subject="Re: Contract Renewal Inquiry",
        body="Thank you for reaching out. We would be glad to renew.",
    )
    assert draft["recipient"] == "client@corp.com"
    assert "draft_id" in draft


def test_email_agent_executor_dispatch():
    res = execute(spec=EMAIL_AGENT, task="Check my unread emails")
    assert res.spec.slug == "native/email-agent"
    assert res.needs_llm is False
    assert "Email Agent:" in res.answer
