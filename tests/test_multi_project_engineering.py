"""Tests for Multi-Project Scheduling, Priority Queues, and State Isolation."""

import pytest
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest
from zero_core.engineering.multi_project import (
    MultiProjectManager,
    ProjectLifecycleState,
    ProjectPriority,
)
from zero_core.engineering.store import EngineeringProjectStore


def test_multi_project_isolation_and_priorities(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    manager = MultiProjectManager(store=store)

    # Create 3 isolated projects
    p1 = ProjectManifest(
        project_id="proj_hr",
        project_name="HR Recruitment AI",
        project_type="NEW_PROJECT",
        description="Recruitment assistant",
        repository_path=str(tmp_path / "hr_repo"),
    )
    p2 = ProjectManifest(
        project_id="proj_trading",
        project_name="Trading Bot",
        project_type="NEW_PROJECT",
        description="Algorithmic trading engine",
        repository_path=str(tmp_path / "trading_repo"),
    )
    p3 = ProjectManifest(
        project_id="proj_finance",
        project_name="Finance Tracker",
        project_type="NEW_PROJECT",
        description="Personal finance tracker",
        repository_path=str(tmp_path / "finance_repo"),
    )

    store.save_project(p1)
    store.save_project(p2)
    store.save_project(p3)

    # Assign distinct priorities
    manager.set_project_priority("proj_hr", ProjectPriority.CRITICAL)
    manager.set_project_priority("proj_trading", ProjectPriority.LOW)
    manager.set_project_priority("proj_finance", ProjectPriority.HIGH)

    summaries = manager.list_projects_overview()
    assert len(summaries) == 3

    # Verify priority sorting: CRITICAL (HR) -> HIGH (Finance) -> LOW (Trading)
    assert summaries[0]["project_id"] == "proj_hr"
    assert summaries[1]["project_id"] == "proj_finance"
    assert summaries[2]["project_id"] == "proj_trading"

    # Verify repository isolation
    assert p1.repository_path != p2.repository_path
    assert p2.repository_path != p3.repository_path


def test_multi_project_pause_resume_and_blocked(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    manager = MultiProjectManager(store=store)

    p1 = ProjectManifest(
        project_id="proj_alpha",
        project_name="Alpha Project",
        project_type="NEW_PROJECT",
        repository_path=str(tmp_path / "alpha_repo"),
        description="Alpha test",
    )
    p1.pending_user_actions = ["GATE 1 approval required"]
    store.save_project(p1)

    # Alpha is waiting on HITL
    state = manager.derive_lifecycle_state(p1)
    assert state == ProjectLifecycleState.WAITING_HITL

    blocked = manager.get_blocked_projects()
    assert len(blocked) == 1
    assert blocked[0]["project_id"] == "proj_alpha"

    # Pause project
    pause_res = manager.pause_project("proj_alpha")
    assert pause_res["status"] == "PAUSED"
    assert manager.derive_lifecycle_state(p1) == ProjectLifecycleState.PAUSED

    # Resume project
    resume_res = manager.resume_project("proj_alpha")
    assert resume_res["status"] == "ACTIVE"


def test_owner_briefing_generation(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    manager = MultiProjectManager(store=store)

    p = ProjectManifest(
        project_id="proj_briefing_test",
        project_name="HR Recruitment AI",
        project_type="NEW_PROJECT",
        repository_path=str(tmp_path / "briefing_repo"),
        description="Recruitment system",
        current_phase=PhaseEnum.PHASE_14_SECURITY,
    )
    p.pending_user_actions = ["Security Gate 4 approval for candidate PII"]
    store.save_project(p)

    briefing = manager.generate_owner_briefing("proj_briefing_test")
    assert briefing["project_name"] == "HR Recruitment AI"
    assert briefing["status"] == "WAITING_HITL"
    assert "Security Gate 4" in briefing["blocker"]
    assert "Credential verification" in briefing["next_after_approval"]
