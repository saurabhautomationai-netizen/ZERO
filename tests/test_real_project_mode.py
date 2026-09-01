"""Tests for Real Project Mode & Existing Project Recognition (Phase 7).

Verifies that ZERO correctly discovers and audits real existing repositories,
classifies components into REUSE/MODIFY/EXTEND without blindly re-scaffolding,
and safely integrates enhancements.
"""

import pytest
from pathlib import Path
from zero_core.agents.project_builder import ProjectBuilderAgent
from zero_core.engineering.manifest import ProjectManifest, PhaseEnum
from zero_core.engineering.workers.native import ProjectBuilderWorker
from zero_core.engineering.workers.base import ProjectContextPackage


def test_existing_project_discovery_classification(tmp_path):
    """Simulates real project discovery with core, app, and tests files."""
    real_repo = tmp_path / "mock_hr_repo"
    real_repo.mkdir()
    (real_repo / "services").mkdir()
    (real_repo / "ui").mkdir()
    (real_repo / "tests").mkdir()
    (real_repo / "docs").mkdir()

    # Existing files
    (real_repo / "app.py").write_text("# Streamlit main app", encoding="utf-8")
    (real_repo / "services" / "supabase_service.py").write_text("# core supabase connection", encoding="utf-8")
    (real_repo / "ui" / "view_candidates.py").write_text("# candidate table and drawer", encoding="utf-8")
    (real_repo / "tests" / "test_candidates.py").write_text("# existing candidate tests", encoding="utf-8")
    (real_repo / "docs" / "ARCHITECTURE.md").write_text("# existing architecture", encoding="utf-8")

    builder = ProjectBuilderAgent()
    audit = builder.audit_existing_project(real_repo)

    assert audit["success"] is True
    classification = audit["classification"]

    # Must classify existing files into REUSE / MODIFY / EXTEND
    assert any("supabase_service.py" in f for f in classification["reuse"])
    assert any("app.py" in f for f in classification["modify"])
    assert len(classification["extend"]) > 0
    assert "Python" in audit["detected_stack"]


def test_project_builder_worker_existing_mode_execution(tmp_path):
    """Verifies ProjectBuilderWorker runs discovery task on real project without scaffolding."""
    real_repo = tmp_path / "hr_app"
    real_repo.mkdir()
    (real_repo / "app.py").write_text("# app entrypoint", encoding="utf-8")
    (real_repo / "core_model.py").write_text("# core models", encoding="utf-8")

    worker = ProjectBuilderWorker()
    context = ProjectContextPackage(
        task_id="t_audit_01",
        project_id=str(real_repo),
        project_name="HR Recruitment AI Assistant",
        current_phase=PhaseEnum.PHASE_1_DISCOVERY,
        task_title="Audit existing project architecture and classify components",
        task_description="Perform discovery and component classification on existing HR repo",
    )

    result = worker.run_task(context)
    assert result.status == "SUCCESS"
    assert "REUSE" in result.analysis
    assert "MODIFY" in result.analysis
    assert "EXTEND" in result.analysis
    assert "docs/DISCOVERY_AUDIT.md" in result.artifacts_created
