"""Unit & integration tests for ProjectBuilderWorker & structured project engineering."""

from pathlib import Path
import pytest

from zero_core.agents.project_builder import DEFAULT_PROJECT_BUILDER, ProjectBuilderAgent
from zero_core.engineering.context_builder import DEFAULT_CONTEXT_BUILDER
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, TaskItem
from zero_core.engineering.workers.base import ProjectContextPackage, WorkerCapability, WorkerResult
from zero_core.engineering.workers.native import ProjectBuilderWorker


@pytest.fixture
def sample_existing_repo(tmp_path):
    repo = tmp_path / "existing_system"
    repo.mkdir()
    (repo / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn>=0.20.0\n", encoding="utf-8")
    core = repo / "core"
    core.mkdir()
    (core / "models.py").write_text("class User: pass\n", encoding="utf-8")
    (core / "config.py").write_text("ENV = 'test'\n", encoding="utf-8")
    routes = repo / "routes"
    routes.mkdir()
    (routes / "api.py").write_text("def get_users(): return []\n", encoding="utf-8")
    return repo


def test_project_builder_worker_capabilities():
    worker = ProjectBuilderWorker()
    assert worker.worker_id == "worker_project_builder"
    assert worker.has_capability(WorkerCapability.SRS)
    assert worker.has_capability(WorkerCapability.ARCHITECTURE)
    assert worker.has_capability(WorkerCapability.PRODUCT_REQUIREMENTS)
    assert worker.has_capability(WorkerCapability.PLANNING)
    assert worker.has_capability(WorkerCapability.DOCUMENTATION)


def test_project_builder_existing_project_discovery(sample_existing_repo):
    builder = ProjectBuilderAgent()
    audit = builder.audit_existing_project(sample_existing_repo)
    assert audit["success"] is True
    assert "Python" in audit["detected_stack"]
    assert "FastAPI" in audit["detected_stack"]
    assert len(audit["classification"]["reuse"]) >= 1
    assert len(audit["classification"]["modify"]) >= 1
    assert "docs/SRS.md" in audit["classification"]["missing"]

    # Test ProjectBuilderWorker running PROJECT_DISCOVERY task
    worker = ProjectBuilderWorker(builder=builder)
    context = ProjectContextPackage(
        task_id="t_disc_01",
        project_id=str(sample_existing_repo),
        project_name="Existing Enterprise System",
        current_phase="PHASE_1_DISCOVERY",
        task_title="Conduct Project Discovery & Codebase Audit",
        task_description="Audit existing repository and classify components into REUSE, MODIFY, EXTEND",
        acceptance_criteria=["Component classification completed", "Reusable core identified"],
    )
    result = worker.run_task(context)
    assert isinstance(result, WorkerResult)
    assert result.is_success
    assert "reusable modules" in result.summary
    assert "REUSE" in result.analysis
    assert "docs/DISCOVERY_AUDIT.md" in result.artifacts_created


def test_project_builder_database_plan():
    worker = ProjectBuilderWorker()
    context = ProjectContextPackage(
        task_id="t_db_01",
        project_id="p_db",
        project_name="Task Management System",
        current_phase="PHASE_7_DATABASE",
        task_title="Formulate Database Plan & Relational Schema",
        task_description="Design Postgres entities and migration strategy",
        acceptance_criteria=["Entity relations defined", "Foreign keys specified"],
    )
    result = worker.run_task(context)
    assert result.is_success
    assert "relational database architecture" in result.summary
    assert "docs/DATABASE_DESIGN.md" in result.files_created
    assert "ON DELETE CASCADE" in result.analysis
    assert result.acceptance_criteria_results["Entity relations defined"] is True


def test_project_builder_api_plan():
    worker = ProjectBuilderWorker()
    context = ProjectContextPackage(
        task_id="t_api_01",
        project_id="p_api",
        project_name="Inventory API Gateway",
        current_phase="PHASE_10_BACKEND",
        task_title="Design REST API Specification",
        task_description="Formulate endpoints, HTTP methods, and payload validation rules",
        acceptance_criteria=["REST routes documented", "JWT auth specified"],
    )
    result = worker.run_task(context)
    assert result.is_success
    assert "REST API schema" in result.summary
    assert "docs/API_SPEC.md" in result.files_created
    assert "GET /api/v1/projects" in result.analysis


def test_project_builder_agent_architecture_plan():
    worker = ProjectBuilderWorker()
    context = ProjectContextPackage(
        task_id="t_ag_01",
        project_id="p_agent",
        project_name="Autonomous Talent Scout",
        current_phase="PHASE_8_AGENTS",
        task_title="Formulate Multi-Agent Architecture",
        task_description="Define agent roles, handoff protocols, and specialist delegation",
        acceptance_criteria=["Agent distribution defined"],
    )
    result = worker.run_task(context)
    assert result.is_success
    assert "multi-agent role distribution" in result.summary
    assert "docs/AGENT_ARCHITECTURE.md" in result.files_created
    assert "Coding Agent" in result.analysis


def test_project_builder_blueprint_generation():
    worker = ProjectBuilderWorker()
    context = ProjectContextPackage(
        task_id="t_bp_01",
        project_id="p_bp",
        project_name="Cloud Asset Monitor",
        current_phase="PHASE_2_SRS",
        task_title="Generate End-to-End System Blueprint",
        task_description="Build autonomous system for cloud asset monitoring",
        acceptance_criteria=["Functional requirements generated", "ADRs formulated"],
    )
    result = worker.run_task(context)
    assert result.is_success
    assert len(result.decisions) >= 2
    assert "docs/SRS.md" in result.files_created
    assert "docs/ARCHITECTURE.md" in result.files_created
    assert "docs/ROADMAP.md" in result.files_created
    assert "Cloud Asset Monitor" in result.summary


def test_project_builder_uses_sanitized_context(tmp_path):
    repo = tmp_path / "leak_test_repo"
    repo.mkdir()
    (repo / ".env").write_text("API_SECRET=fake_secret_key_12345\n", encoding="utf-8")
    (repo / "service.py").write_text("API_TOKEN = 'sk-proj-faketestsecret1234567890abcdef'\n", encoding="utf-8")

    manifest = ProjectManifest(
        project_id="p_sec_test",
        project_name="Secure System",
        description="Security verification",
        repository_path=str(repo),
    )
    task = TaskItem(
        task_id="t_sec_01",
        milestone_id="m1",
        title="Analyze repository architecture",
        description="Inspect existing services",
    )

    # Build context using Phase 2 context builder
    context = DEFAULT_CONTEXT_BUILDER.build_context(manifest, task, worker=ProjectBuilderWorker())
    
    worker = ProjectBuilderWorker()
    result = worker.run_task(context)
    assert result.is_success
    
    # Assert no fake secret appears in WorkerResult
    result_str = str(result.to_dict())
    assert "fake_secret_key_12345" not in result_str
    assert "sk-proj-faketestsecret1234567890abcdef" not in result_str
