"""Unit and integration tests for UI/UX Department & Design Review Engine (Phase 3)."""

from pathlib import Path
import pytest

from zero_core.agents.loop_engineering import LoopEngineeringAgent
from zero_core.approval.engine import ApprovalPolicyEngine
from zero_core.engineering.checkpoints import CheckpointManager
from zero_core.engineering.context_builder import DEFAULT_CONTEXT_BUILDER
from zero_core.engineering.departments.registry import DEFAULT_DEPARTMENT_REGISTRY
from zero_core.engineering.departments.uiux import (
    DEFAULT_UIUX_COORDINATOR,
    UIDesignPackage,
    UIReviewFinding,
    UIReviewResult,
    UIUXDepartmentCoordinator,
)
from zero_core.engineering.manifest import ApprovalGateType, PhaseEnum, ProjectManifest, ProjectStatus, TaskItem
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.engineering.workers.base import ProjectContextPackage, WorkerCapability, WorkerResult
from zero_core.engineering.workers.registry import DEFAULT_WORKER_REGISTRY, bootstrap_native_workers


@pytest.fixture
def clean_loop_agent(tmp_path):
    store_dir = tmp_path / "engineering_projects"
    ckpt_dir = tmp_path / "checkpoints"
    store = EngineeringProjectStore(storage_dir=store_dir)
    checkpoints = CheckpointManager(checkpoint_dir=ckpt_dir)
    return LoopEngineeringAgent(store=store, checkpoints=checkpoints)


def test_uiux_department_registration():
    bootstrap_native_workers(DEFAULT_WORKER_REGISTRY)
    worker = DEFAULT_WORKER_REGISTRY.get("worker_uiux_designer")
    assert worker is not None
    assert worker.has_capability(WorkerCapability.UI_DESIGN)
    assert worker.has_capability(WorkerCapability.UX_ARCHITECTURE)

    dept = DEFAULT_DEPARTMENT_REGISTRY.get("design")
    assert dept is not None
    assert dept.lead_worker_id == "worker_uiux_designer"


def test_page_inventory_generation():
    coordinator = UIUXDepartmentCoordinator()
    
    # HR Recruitment context
    context_hr = ProjectContextPackage(
        task_id="t_hr",
        project_id="p_hr",
        project_name="AI Talent Scout",
        current_phase="PHASE_5_UIUX",
        task_title="Design HR recruitment experience",
        task_description="Candidate ATS portal with job pipelines",
    )
    pages_hr = coordinator.generate_page_inventory(context_hr)
    page_names_hr = [p["name"] for p in pages_hr]
    assert "Dashboard" in page_names_hr
    assert "Candidates" in page_names_hr
    assert "Jobs" in page_names_hr
    assert "Pipeline" in page_names_hr

    # Trading terminal context
    context_trading = ProjectContextPackage(
        task_id="t_trade",
        project_id="p_trade",
        project_name="MT5 SMC Terminal",
        current_phase="PHASE_5_UIUX",
        task_title="Design trading terminal interface",
        task_description="Forex portfolio and live signals",
    )
    pages_trading = coordinator.generate_page_inventory(context_trading)
    page_names_trading = [p["name"] for p in pages_trading]
    assert "Dashboard" in page_names_trading
    assert "Trading Terminal" in page_names_trading
    assert "Strategy Signals" in page_names_trading


def test_design_system_generation():
    coordinator = UIUXDepartmentCoordinator()
    ds = coordinator.generate_design_system("Quantum SaaS")
    
    assert "colors" in ds
    assert "typography" in ds
    assert "spacing" in ds
    assert "motion" in ds
    assert ds["colors"]["background_primary"] == "#0A0D14"
    assert "reduced_motion" in ds["motion"]


def test_interactive_prototype_generation():
    coordinator = UIUXDepartmentCoordinator()
    pages = [{"name": "Dashboard", "path": "/dashboard", "purpose": "Overview"}]
    ds = coordinator.generate_design_system("Test App")
    html = coordinator.generate_interactive_prototype("Test App", pages, ds)
    
    assert "<!DOCTYPE html>" in html
    assert "Test App Prototype" in html
    assert "/dashboard" in html
    assert "HITL Gate 2 Ready" in html


def test_accessibility_and_finish_gate_review():
    coordinator = UIUXDepartmentCoordinator()
    
    # Healthy design package
    pkg_valid = UIDesignPackage(
        project_id="p_valid",
        project_name="Valid App",
        pages=[{"name": "Home", "path": "/", "purpose": "Home page"}],
        design_system=coordinator.generate_design_system("Valid App"),
    )
    review_valid = coordinator.review_design_package(pkg_valid)
    assert review_valid.is_pass
    assert review_valid.score >= 80

    # Package with zero-contrast failure
    bad_ds = coordinator.generate_design_system("Bad App")
    bad_ds["colors"]["background_primary"] = "#ffffff"
    bad_ds["colors"]["text_primary"] = "#ffffff"  # Zero contrast
    pkg_bad = UIDesignPackage(
        project_id="p_bad",
        project_name="Bad App",
        pages=[{"name": "Home", "path": "/", "purpose": "Home page"}],
        design_system=bad_ds,
    )
    review_bad = coordinator.review_design_package(pkg_bad)
    assert not review_bad.is_pass
    assert any(f.category == "ACCESSIBILITY" for f in review_bad.findings)


def test_ui_audit_existing_project():
    coordinator = UIUXDepartmentCoordinator()
    context = ProjectContextPackage(
        task_id="t_audit",
        project_id="p_audit",
        project_name="Legacy Portal",
        current_phase="PHASE_5_UIUX",
        task_title="Audit existing UI assets",
        task_description="Review frontend components",
        relevant_files={
            "src/styles/base.css": "body { margin: 0; }",
            "src/components/card.jsx": "export const Card = () => <div />;",
            "src/pages/old_view.html": "<html><body>Old</body></html>",
        },
    )
    audit = coordinator.audit_existing_ui(context)
    assert audit["is_existing_ui"] is True
    assert "src/styles/base.css" in audit["classification"]["keep"]
    assert "src/components/card.jsx" in audit["classification"]["improve"]
    assert "src/pages/old_view.html" in audit["classification"]["redesign"]


def test_bounded_ui_revision_loop():
    coordinator = UIUXDepartmentCoordinator()
    context = ProjectContextPackage(
        task_id="t_rev",
        project_id="proj_bounded_test",
        project_name="Iterative App",
        current_phase="PHASE_5_UIUX",
        task_title="Design interface iteration",
        task_description="Produce refined layout",
    )

    # Revisions 1, 2, 3 proceed normally
    res1 = coordinator.run_task(context)
    assert res1.is_success
    assert coordinator.revision_counter["proj_bounded_test"] == 1

    res2 = coordinator.run_task(context)
    assert res2.is_success
    assert coordinator.revision_counter["proj_bounded_test"] == 2

    res3 = coordinator.run_task(context)
    assert res3.is_success
    assert coordinator.revision_counter["proj_bounded_test"] == 3

    # Revision 4 exceeds limit -> Halts and escalates to HITL
    res4 = coordinator.run_task(context)
    assert res4.status == "BLOCKED"
    assert res4.requires_human is True
    assert "exceeded maximum limit" in res4.summary


def test_hitl_gate_2_stops_before_frontend_implementation(clean_loop_agent, tmp_path):
    """END-TO-END TEST:
    Verifies that Loop Engineering Agent progresses through Inception, Feature Scope (Gate 1),
    SRS, Architecture, Scaffolding, and UI/UX Department, then STOPS at Gate 2.
    Asserts NO production frontend implementation code exists before Gate 2 approval.
    """
    repo = tmp_path / "task_saas_repo"
    repo.mkdir()

    agent = clean_loop_agent

    # 1. Intake
    manifest = agent.intake_project(idea="Build an autonomous AI Task Manager SaaS", repo_path=str(repo))
    assert manifest.project_status == ProjectStatus.INTAKE

    # 2. Discovery
    disc_res = agent.run_discovery(manifest)
    assert disc_res["status"] == "APPROVAL_PENDING"
    assert disc_res["gate"] == "FEATURE_SCOPE"

    # 3. Approve Gate 1: Feature Scope -> Advances to SRS, Architecture, Scaffolding & UI/UX
    gate1_res = agent.approve_feature_scope(manifest.project_id)
    assert gate1_res["status"] == "APPROVAL_PENDING"
    assert gate1_res["gate"] == ApprovalGateType.UI_UX_DESIGN.value
    assert gate1_res["current_phase"] == PhaseEnum.PHASE_5_UIUX.value

    # Verify manifest state after UI/UX generation
    updated_manifest = agent.store.get_project(manifest.project_id)
    assert updated_manifest.current_phase == PhaseEnum.PHASE_5_UIUX
    assert updated_manifest.uiux_status == "APPROVAL_PENDING"
    assert updated_manifest.uiux_worker_assignments["lead"] == "worker_uiux_designer"
    assert "docs/UIUX_SPEC.md" in updated_manifest.uiux_artifacts
    assert updated_manifest.uiux_review_status == "PASS"

    # Verify design docs exist on disk
    target_repo = Path(updated_manifest.repository_path)
    assert (target_repo / "docs" / "SRS.md").exists()
    assert (target_repo / "docs" / "ARCHITECTURE.md").exists()
    assert (target_repo / "docs" / "UIUX_SPEC.md").exists()

    # CRITICAL INVARIANT: Production backend & frontend code MUST NOT be implemented before Gate 2 approval!
    assert updated_manifest.database_status == "PENDING"
    assert updated_manifest.backend_status == "PENDING"
    assert updated_manifest.frontend_status == "PENDING"
    assert updated_manifest.testing_status == "PENDING"

    # 4. Now simulate Human Gate 2 Approval -> Implementation can proceed!
    gate2_res = agent.approve_uiux_and_build(manifest.project_id)
    assert gate2_res["status"] == "APPROVAL_PENDING"  # Next gate (Deployment/Security)
    
    post_build_manifest = agent.store.get_project(manifest.project_id)
    assert post_build_manifest.uiux_status == "COMPLETED"
    assert post_build_manifest.database_status == "COMPLETED"
    assert post_build_manifest.backend_status == "COMPLETED"
    assert post_build_manifest.frontend_status == "COMPLETED"
