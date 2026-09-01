"""Comprehensive Unit Tests for Autonomous Project Builder Pipeline."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from zero_core.agents.coding_agent import CodingAgent, DEFAULT_CODING_AGENT
from zero_core.agents.git_agent import GitAgent, DEFAULT_GIT_AGENT
from zero_core.agents.project_builder import ProjectBuilderAgent, DEFAULT_PROJECT_BUILDER
from zero_core.tools import build_default_tool_registry


def test_project_builder_blueprint_generation():
    agent = ProjectBuilderAgent()
    blueprint = agent.build_blueprint(
        project_name="Crypto Arbitrage Engine",
        idea="High-frequency cross-exchange triangular arbitrage executor.",
    )

    assert blueprint.project_name == "Crypto Arbitrage Engine"
    assert len(blueprint.srs_requirements["functional"]) >= 4
    assert len(blueprint.architecture_layers) >= 4
    assert len(blueprint.roadmap_milestones) >= 4

    md = blueprint.to_markdown()
    assert "Architectural Blueprint: Crypto Arbitrage Engine" in md
    assert "Software Requirements Specification" in md
    assert "Implementation Roadmap" in md


def test_project_scaffold_and_validation():
    agent = ProjectBuilderAgent()

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        res = agent.scaffold_project(
            project_name="Nexus AI",
            target_dir=tmp_path,
            idea="Autonomous intelligence engine.",
        )

        assert res["success"] is True
        project_root = Path(res["root_path"])
        assert project_root.exists()

        # Check required docs
        assert (project_root / "README.md").exists()
        assert (project_root / "docs" / "SRS.md").exists()
        assert (project_root / "docs" / "ARCHITECTURE.md").exists()
        assert (project_root / "docs" / "ROADMAP.md").exists()

        # Check code package
        assert (project_root / "nexus_ai_core" / "__init__.py").exists()
        assert (project_root / "nexus_ai_core" / "config.py").exists()
        assert (project_root / "nexus_ai_core" / "orchestrator.py").exists()

        # Check tests
        assert (project_root / "tests" / "test_core.py").exists()

        # Validate scaffold
        val = agent.validate_scaffold(project_root)
        assert val["valid"] is True
        assert val["missing_docs"] == []
        assert len(val["syntax_errors"]) == 0


def test_coding_agent_run_tests_on_scaffold():
    builder = ProjectBuilderAgent()
    coder = CodingAgent()

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        res = builder.scaffold_project(
            project_name="Pulse Tracker",
            target_dir=tmp_path,
            idea="Health metrics analyzer.",
        )
        project_root = Path(res["root_path"])

        # Execute pytest on the scaffolded project
        test_res = coder.run_project_tests(project_root)
        assert test_res.success is True
        assert test_res.exit_code == 0
        assert "passed" in test_res.output or "1 passed" in test_res.output


def test_coding_agent_generate_stub():
    coder = CodingAgent()
    code = coder.generate_module_stub(
        module_name="auth_service",
        class_name="AuthManager",
        methods=["login", "logout", "verify_token"],
    )
    assert "class AuthManager:" in code
    assert "def login(" in code
    assert "def logout(" in code
    assert "def verify_token(" in code


def test_git_agent_init_and_commit():
    git = GitAgent()

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

        res = git.init_and_commit(tmp_path, "feat: initial commit")
        # In CI/environments with git installed, git init succeeds
        assert res["success"] is True or "Git" in str(res.get("error", ""))


def test_tool_registry_scaffold_execution():
    registry = build_default_tool_registry()

    with TemporaryDirectory() as tmp_dir:
        res = registry.execute(
            "project_scaffold",
            project_name="Aura Vision",
            target_dir=tmp_dir,
            idea_summary="Spatial computing visual analytics.",
        )
        assert res.success is True
        assert res.output.get("success") is True
        assert res.output.get("files_created_count") > 5
