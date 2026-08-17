from __future__ import annotations

from zero_core.agents.research_agent import (
    DEFAULT_RESEARCH_AGENT,
    ResearchAgent,
    ResearchReport,
    ResearchSource,
)
from zero_core.executors import execute
from zero_core.native_agents import RESEARCH_AGENT


def test_research_agent_synthesize_report():
    agent = ResearchAgent()
    src = ResearchSource(
        source_id="src_01",
        title="Agentic AI Architecture Whitepaper",
        url_or_ref="https://arxiv.org/abs/2401.00001",
        snippet="Decoupled state machines provide 40% higher fault tolerance.",
        author="DeepMind Team",
    )
    agent.add_source(src)

    report = agent.synthesize_research("Modular Multi-Agent Systems")
    md = report.to_markdown()

    assert "Modular Multi-Agent Systems" in md
    assert "Executive Summary" in md
    assert "Agentic AI Architecture Whitepaper" in md
    assert "DeepMind Team" in md
    assert "Recommendations" in md


def test_research_agent_evaluate_tech_options():
    agent = ResearchAgent()
    candidates = [
        {
            "name": "FastAPI + Pydantic",
            "advantages": "High performance, async support, auto OpenAPI",
            "tradeoffs": "Requires ASGI server setup",
            "verdict": "Adopt",
        },
        {
            "name": "Flask",
            "advantages": "Simple, synchronous",
            "tradeoffs": "No built-in async validation",
            "verdict": "Hold",
        },
    ]

    matrix = agent.evaluate_tech_options(
        criteria=["Latency", "Schema Validation", "Maintainability"],
        candidates=candidates,
    )
    assert "Technology Evaluation Matrix" in matrix
    assert "FastAPI + Pydantic" in matrix
    assert "Adopt" in matrix


def test_research_agent_executor_dispatch():
    res = execute(spec=RESEARCH_AGENT, task="Autonomous Agent Memory Systems")
    assert res.spec.slug == "native/research-agent"
    assert res.needs_llm is False
    assert "Research Report: Autonomous Agent Memory Systems" in res.answer
