from __future__ import annotations

import os
from zero_core.interfaces.web.handlers import handle_task
from zero_core.llm import (
    DEFAULT_LLM_MANAGER,
    BaseLLMClient,
    GeminiLLMClient,
    LLMClientManager,
    MockOfflineLLMClient,
    OllamaLLMClient,
    OpenAILLMClient,
)


class CustomTestClient(BaseLLMClient):
    def generate(self, system_prompt: str, user_prompt: str, model=None) -> str:
        return f"CUSTOM_MODEL: Answered '{user_prompt}'"


def test_mock_offline_llm_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    manager = LLMClientManager()
    persona = "---\nname: Python Architect\n---\nSystem instructions."
    response = manager.call_specialist(persona=persona, task="Refactor async loop")
    assert "Python Architect Response" in response
    assert "Refactor async loop" in response


def test_custom_llm_client_injection():
    manager = LLMClientManager(client=CustomTestClient())
    response = manager.call_specialist(
        persona="Persona text",
        task="Optimize database indexing",
    )
    assert response == "CUSTOM_MODEL: Answered 'Optimize database indexing'"


def test_gemini_client_missing_key_error():
    client = GeminiLLMClient(api_key="")
    ans = client.generate(system_prompt="sys", user_prompt="usr")
    assert "GEMINI_API_KEY is not set" in ans


def test_openai_client_missing_key_error():
    client = OpenAILLMClient(api_key="")
    ans = client.generate(system_prompt="sys", user_prompt="usr")
    assert "OPENAI_API_KEY is not set" in ans


def test_llm_manager_auto_detection(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    manager = LLMClientManager()
    assert isinstance(manager.client, MockOfflineLLMClient)

    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")
    assert isinstance(manager.client, GeminiLLMClient)

    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    assert isinstance(manager.client, OpenAILLMClient)


def test_handle_task_with_auto_invoke_llm(monkeypatch, fake_agency_root):
    from pathlib import Path
    from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
    from zero_core.native_agents import ALL_NATIVE_AGENTS
    from zero_core.orchestrator import Orchestrator
    import zero_core.interfaces.web.handlers as handlers

    adapter = AgencyAgentsAdapter(
        root=fake_agency_root,
        divisions=["engineering"],
        inventory_snapshot=Path("/nonexistent"),
    )
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)
    orch = Orchestrator(registry=registry)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setattr(handlers, "build_registry", lambda: registry)
    monkeypatch.setattr(handlers, "build_orchestrator", lambda: orch)

    res = handle_task("I need help with database architecture scalability", auto_invoke_llm=True)
    assert res["needs_llm"] is True
    assert res["answer"] is not None
    assert "Fake Backend Architect Response" in res["answer"]
