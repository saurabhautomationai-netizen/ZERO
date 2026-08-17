from __future__ import annotations

from pathlib import Path

import zero_core.interfaces.web.handlers as handlers
from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
from zero_core.native_agents import ALL_NATIVE_AGENTS
from zero_core.orchestrator import Orchestrator


def _patch_backends(monkeypatch, fake_agency_root):
    adapter = AgencyAgentsAdapter(
        root=fake_agency_root,
        divisions=["engineering", "finance"],
        inventory_snapshot=Path("/nonexistent"),
    )
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)
    orch = Orchestrator(registry=registry)

    monkeypatch.setattr(handlers, "build_registry", lambda: registry)
    monkeypatch.setattr(handlers, "build_orchestrator", lambda: orch)
    return registry, orch


def test_handle_task_rejects_empty_task():
    assert handlers.handle_task("") == {"error": "task must be a non-empty string"}
    assert handlers.handle_task("   ") == {"error": "task must be a non-empty string"}


def test_handle_task_returns_selected_and_answer(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)
    monkeypatch.delenv("FINANCE_DB_URL", raising=False)

    result = handlers.handle_task("What did I spend on subscriptions last month?")

    assert result["task"] == "What did I spend on subscriptions last month?"
    assert result["selected"]["slug"] == "native/finance-agent"
    assert result["needs_llm"] is False
    assert "not configured yet" in result["answer"].lower()
    assert result["persona"] is None


def test_handle_task_agency_specialist_includes_persona(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)

    result = handlers.handle_task("I need help with database architecture scalability", auto_invoke_llm=False)

    assert result["selected"]["source"] == "agency"
    assert result["needs_llm"] is True
    assert result["answer"] is None
    assert "Fake Backend Architect" in result["persona"]


def test_handle_list_agents_filters_by_division(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)

    result = handlers.handle_list_agents(division="finance")

    assert result["agency_count"] == 1
    assert result["agency"][0]["name"] == "Fake Financial Analyst"
    assert len(result["native"]) == len(ALL_NATIVE_AGENTS)


def test_handle_get_agent_found_and_not_found(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)

    found = handlers.handle_get_agent("engineering/engineering-fake-backend-architect")
    assert found is not None
    assert found["name"] == "Fake Backend Architect"

    assert handlers.handle_get_agent("does/not-exist") is None


def test_handle_get_agent_finds_native_agents_too(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)
    result = handlers.handle_get_agent("native/trading-agent")
    assert result is not None
    assert result["source"] == "native"
