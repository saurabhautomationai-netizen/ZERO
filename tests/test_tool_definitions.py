"""Comprehensive Unit Tests for Tool Definitions across all operational domains."""

import pytest
from zero_core.bootstrap import build_tool_registry
from zero_core.tools import (
    ALL_BUILTIN_TOOLS,
    FILESYSTEM_TOOLS,
    FINANCE_TOOLS,
    PROJECT_TOOLS,
    TRADING_TOOLS,
    WORKSPACE_TOOLS,
    ToolRegistry,
    build_default_tool_registry,
)


def test_tool_registry_initialization():
    registry = build_default_tool_registry()
    tools = registry.list_tools()
    assert len(tools) >= 14
    schemas = registry.get_schemas()
    assert len(schemas) == len(tools)

    tool_names = [t.name for t in tools]
    assert "finance_recent_transactions" in tool_names
    assert "finance_category_totals" in tool_names
    assert "trading_mt5_account_status" in tool_names
    assert "trading_bot_signals" in tool_names
    assert "trading_coach_query" in tool_names
    assert "trading_preflight_check" in tool_names
    assert "workspace_calendar_agenda" in tool_names
    assert "workspace_unread_emails" in tool_names
    assert "workspace_create_email_draft" in tool_names
    assert "workspace_schedule_event" in tool_names
    assert "workspace_send_email" in tool_names
    assert "project_search_knowledge" in tool_names
    assert "project_git_status" in tool_names


def test_finance_tools_execution():
    registry = build_default_tool_registry()

    # finance_recent_transactions
    res = registry.execute("finance_recent_transactions", limit=5)
    assert res.success is True
    assert isinstance(res.output, list)

    # finance_category_totals
    res_tot = registry.execute("finance_category_totals")
    assert res_tot.success is True
    assert isinstance(res_tot.output, list)


def test_trading_tools_execution():
    registry = build_default_tool_registry()

    # mt5 account status
    res_mt5 = registry.execute("trading_mt5_account_status")
    assert res_mt5.success is True
    assert "balance" in res_mt5.output
    assert "equity" in res_mt5.output

    # trading bot signals
    res_sig = registry.execute("trading_bot_signals")
    assert res_sig.success is True
    assert "summary" in res_sig.output

    # trading coach query
    res_coach = registry.execute("trading_coach_query", query="rules")
    assert res_coach.success is True
    assert "Rule" in res_coach.output or "SMC" in res_coach.output

    # trading preflight check
    res_pf = registry.execute(
        "trading_preflight_check",
        symbol="XAUUSD",
        bias="BULLISH",
        action="BUY",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2660.0,
    )
    assert res_pf.success is True
    assert "Pre-Flight" in res_pf.output


def test_workspace_tools_execution():
    registry = build_default_tool_registry()

    # calendar agenda
    res_cal = registry.execute("workspace_calendar_agenda", hours_ahead=24)
    assert res_cal.success is True
    assert isinstance(res_cal.output, str)

    # unread emails
    res_em = registry.execute("workspace_unread_emails", max_results=5)
    assert res_em.success is True
    assert isinstance(res_em.output, str)

    # create draft
    res_draft = registry.execute(
        "workspace_create_email_draft",
        recipient="partner@example.com",
        subject="Meeting Follow-up",
        body="Attached is the summary from today's discussion.",
    )
    assert res_draft.success is True
    assert res_draft.output.get("status") == "draft_created"

    # schedule event
    res_sched = registry.execute(
        "workspace_schedule_event",
        title="Strategy Sync",
        start_time="2026-08-20T10:00:00Z",
        end_time="2026-08-20T11:00:00Z",
    )
    assert res_sched.success is True
    assert res_sched.output.get("success") is True

    # send email (destructive / HIGH risk tool)
    res_send = registry.execute(
        "workspace_send_email",
        recipient="ceo@example.com",
        subject="Important Update",
        body="All systems are operating normally.",
    )
    assert res_send.success is True
    assert res_send.output.get("status") == "sent"


def test_project_tools_execution():
    registry = build_default_tool_registry()

    # search knowledge
    res_proj = registry.execute("project_search_knowledge", query="zero")
    assert res_proj.success is True
    assert "ZERO" in res_proj.output or "Architecture" in res_proj.output or "Project" in res_proj.output

    # git status
    res_git = registry.execute("project_git_status", include_commits=True)
    assert res_git.success is True
    assert "branch" in res_git.output.lower() or "working tree" in res_git.output.lower()


def test_tool_argument_validation_errors():
    registry = build_default_tool_registry()

    # Invalid missing required argument
    res_err = registry.execute("workspace_create_email_draft", recipient="invalid_only")
    assert res_err.success is False
    assert "validation error" in res_err.error.lower()
