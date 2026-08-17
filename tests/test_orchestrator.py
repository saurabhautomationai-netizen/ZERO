from __future__ import annotations

from pathlib import Path

from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
from zero_core.native_agents import ALL_NATIVE_AGENTS
from zero_core.orchestrator import Orchestrator


def _registry(fake_agency_root: Path) -> AgentRegistry:
    adapter = AgencyAgentsAdapter(
        root=fake_agency_root,
        divisions=["engineering", "finance"],
        inventory_snapshot=Path("/nonexistent"),
    )
    return AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)


def test_orchestrator_runs_without_langgraph_installed(fake_agency_root):
    """This suite intentionally doesn't require langgraph — Orchestrator must
    still produce a correct decision via the pure-Python fallback path.
    """
    orch = Orchestrator(registry=_registry(fake_agency_root))
    result = orch.run("What did I spend on subscriptions last month?")

    assert result.selected is not None
    assert result.selected.slug == "native/finance-agent"
    assert "Selected: Finance Agent" in result.explain()


def test_orchestrator_no_match_is_handled_gracefully(fake_agency_root):
    orch = Orchestrator(registry=_registry(fake_agency_root))
    result = orch.run("xyz")  # nothing should match a nonsense 3-char task
    assert result.selected is None
    assert "No specialist matched" in result.explain()


def test_orchestrator_execute_produces_real_answer_for_native_agent(fake_agency_root, monkeypatch):
    monkeypatch.delenv("FINANCE_DB_URL", raising=False)
    orch = Orchestrator(registry=_registry(fake_agency_root))

    result = orch.execute("What did I spend on subscriptions last month?")

    assert result.needs_llm is False
    assert result.spec.slug == "native/finance-agent"
    assert "not configured yet" in result.answer.lower()  # honest, no live DB in tests


def test_orchestrator_execute_hands_off_persona_for_agency_specialist(fake_agency_root):
    orch = Orchestrator(registry=_registry(fake_agency_root))

    result = orch.execute("I need help with database architecture scalability")

    assert result.needs_llm is True
    assert result.answer is None
    assert result.persona is not None
    assert "Fake Backend Architect" in result.persona


def test_orchestrator_execute_no_match(fake_agency_root):
    orch = Orchestrator(registry=_registry(fake_agency_root))
    result = orch.execute("xyz")
    assert result.needs_llm is False
    assert "No specialist matched" in result.answer
