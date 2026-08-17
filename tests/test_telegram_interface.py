from __future__ import annotations

from pathlib import Path
from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
from zero_core.approval import ApprovalPolicyEngine, RiskLevel
from zero_core.interfaces.telegram import (
    TelegramBotHandler,
    format_agent_card,
    format_approval_prompt,
    format_task_response,
)
from zero_core.native_agents import ALL_NATIVE_AGENTS
from zero_core.orchestrator import Orchestrator


def _build_test_bot(fake_agency_root):
    adapter = AgencyAgentsAdapter(
        root=fake_agency_root,
        divisions=["engineering", "finance"],
        inventory_snapshot=Path("/nonexistent"),
    )
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)
    orch = Orchestrator(registry=registry)
    approval = ApprovalPolicyEngine()
    return TelegramBotHandler(orchestrator=orch, approval_engine=approval)


def test_telegram_command_start_and_help(fake_agency_root):
    bot = _build_test_bot(fake_agency_root)
    res = bot.handle_command("/start")
    assert "Welcome to ZERO" in res
    assert "/task" in res

    help_res = bot.handle_command("/help")
    assert "Available Commands" in help_res


def test_telegram_command_agents_and_status(fake_agency_root):
    bot = _build_test_bot(fake_agency_root)
    agents_res = bot.handle_command("/agents")
    assert "ZERO Agent Catalog" in agents_res
    assert "Finance Agent" in agents_res

    status_res = bot.handle_command("/status")
    assert "Operational" in status_res


def test_telegram_message_task_dispatch(fake_agency_root, monkeypatch):
    monkeypatch.delenv("FINANCE_DB_URL", raising=False)
    bot = _build_test_bot(fake_agency_root)

    res = bot.handle_message("What did I spend on subscriptions last month?")
    assert "Finance Agent" in res
    assert "not configured yet" in res.lower()


def test_telegram_callback_approval_flow():
    approval = ApprovalPolicyEngine()
    req = approval.evaluate("tool", "delete_db", declared_risk=RiskLevel.HIGH)

    bot = TelegramBotHandler(approval_engine=approval)
    prompt = format_approval_prompt(req)
    assert "inline_keyboard" in prompt["reply_markup"]

    callback_res = bot.handle_callback(f"approve:{req.request_id}")
    assert "approved" in callback_res.lower()
    assert approval.is_action_permitted(req.request_id) is True
