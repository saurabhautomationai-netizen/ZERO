from __future__ import annotations

from zero_core.agents.automation_agent import (
    DEFAULT_AUTOMATION_AGENT,
    AutomationAgent,
    WorkflowTriggerPayload,
)
from zero_core.executors import execute
from zero_core.native_agents import AUTOMATION_AGENT


def test_automation_agent_list_and_summarize():
    agent = AutomationAgent()
    wfs = agent.list_workflows()
    assert len(wfs) >= 2
    assert any(w["id"] == "finance_tracker" for w in wfs)

    summary = agent.summarize_automations()
    assert "Connected Automations" in summary
    assert "Zero Finance Tracker" in summary
    assert "118 nodes" in summary


def test_automation_agent_format_trigger():
    agent = AutomationAgent(n8n_base_url="https://n8n.my-domain.com")
    payload_data = {"event": "new_receipt", "amount": 42.50, "vendor": "Office Supplies"}

    trigger = agent.format_trigger("finance_tracker", payload_data)
    assert trigger.status == "TRIGGERED"
    assert trigger.target_webhook_url == "https://n8n.my-domain.com/webhook/finance_tracker"
    assert trigger.payload["amount"] == 42.50


def test_automation_agent_executor_dispatch():
    res = execute(spec=AUTOMATION_AGENT, task="List running automations")
    assert res.spec.slug == "native/automation-agent"
    assert res.needs_llm is False
    assert "Connected Automations" in res.answer
