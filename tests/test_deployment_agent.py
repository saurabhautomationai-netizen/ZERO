from __future__ import annotations

from zero_core.agents.deployment_agent import (
    DEFAULT_DEPLOYMENT_AGENT,
    DeploymentAgent,
    SystemHealthReport,
)
from zero_core.executors import execute
from zero_core.native_agents import DEPLOYMENT_AGENT


def test_deployment_agent_health_check():
    agent = DeploymentAgent()
    report = agent.run_health_check()

    assert report.overall_status in ("HEALTHY", "DEGRADED")
    assert len(report.subsystems) >= 4

    md = report.to_markdown()
    assert "Subsystem Health & Diagnostics" in md
    assert "Agency-agents Catalog" in md
    assert "Tool Registry" in md
    assert "Vector RAG Engine" in md


def test_deployment_agent_executor_dispatch():
    res = execute(spec=DEPLOYMENT_AGENT, task="Check system diagnostics and health")
    assert res.spec.slug == "native/deployment-agent"
    assert res.needs_llm is False
    assert "Subsystem Diagnostic Matrix" in res.answer
