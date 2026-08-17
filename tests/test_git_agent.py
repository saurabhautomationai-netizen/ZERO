from __future__ import annotations

from zero_core.agents.git_agent import (
    DEFAULT_GIT_AGENT,
    GitAgent,
    GitStatusSummary,
)
from zero_core.executors import execute
from zero_core.native_agents import GIT_AGENT


def test_git_agent_safety_guardrails():
    agent = GitAgent()
    assert agent.is_operation_safe("git status") is True
    assert agent.is_operation_safe("git log -n 5") is True
    assert agent.is_operation_safe("git commit -m 'feat: add agent'") is True

    # Destructive operations must be flagged as unsafe
    assert agent.is_operation_safe("git push origin main --force") is False
    assert agent.is_operation_safe("git reset --hard HEAD~1") is False
    assert agent.is_operation_safe("git clean -fd") is False
    assert agent.is_operation_safe("git branch -D feature") is False


def test_git_agent_conventional_commit():
    agent = GitAgent()
    msg = agent.generate_conventional_commit("feat", "agents", "Add Coding and Git Agents.")
    assert msg == "feat(agents): Add Coding and Git Agents"


def test_git_agent_inspect_status():
    agent = GitAgent()
    status_clean = agent.inspect_status("main")
    assert status_clean.is_clean is True
    assert "clean" in status_clean.summary()

    status_dirty = agent.inspect_status(
        "feature/agents",
        mock_changes={
            "staged": ["zero_core/agents/git_agent.py"],
            "unstaged": ["README.md"],
            "untracked": ["tests/test_git_agent.py"],
        },
    )
    assert status_dirty.is_clean is False
    summary = status_dirty.summary()
    assert "feature/agents" in summary
    assert "[staged] zero_core/agents/git_agent.py" in summary


def test_git_agent_executor_dispatch():
    res = execute(spec=GIT_AGENT, task="Check working tree")
    assert res.spec.slug == "native/git-agent"
    assert res.needs_llm is False
    assert "On branch:" in res.answer
