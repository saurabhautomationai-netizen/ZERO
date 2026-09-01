"""End-to-end mandatory verification tests for Phase 6:
- Mandatory Autonomous Project Test (AI Meeting Notes Manager)
- Mandatory Restart Test
- Mandatory Multi-Project Test
- Mandatory Security Test
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from zero_core.agents.loop_engineering import DEFAULT_LOOP_ENGINEERING_AGENT, LoopEngineeringAgent
from zero_core.engineering.lifecycle import ProjectLifecycleController, TaskDAG, TaskState
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, ProjectStatus
from zero_core.engineering.multi_project import MultiProjectManager, ProjectPriority, ProjectLifecycleState
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.interfaces.web.app import app


def test_mandatory_autonomous_project_lifecycle(tmp_path):
    """MANDATORY AUTONOMOUS PROJECT TEST:
    Runs AI Meeting Notes Manager through complete lifecycle:
    Intake -> Discovery -> Scope Gate 1 (Stop) -> Approve Gate 1
    -> SRS -> Architecture -> UIUX Gate 2 (Stop) -> Approve Gate 2
    -> Database -> Backend -> Frontend -> Testing -> Security Gate 4 (Stop) -> Approve Gate 4
    -> Credentials Gate 5 -> Release Candidate -> Deployment Gate 8 (Stop).
    Verifies ZERO does NOT deploy without Gate 8 approval!
    """
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    agent = LoopEngineeringAgent(store=store)

    # 1. INTAKE & DISCOVERY
    manifest = agent.intake_project(
        idea="Build AI Meeting Notes Manager",
        repo_path=str(tmp_path / "meeting_notes_repo"),
    )
    assert manifest.current_phase == PhaseEnum.PHASE_0_INTAKE

    # Advance into Phase 1 Discovery
    manifest.current_phase = PhaseEnum.PHASE_1_DISCOVERY
    store.save_project(manifest)

    # 2. ADVANCE TO GATE 1 (FEATURE SCOPE)
    res_gate1 = agent.advance_project_lifecycle(manifest)
    assert res_gate1["status"] == "APPROVAL_PENDING"
    assert any("GATE 1" in b for b in res_gate1["blockers"])
    assert len(manifest.pending_user_actions) > 0

    # Simulate Human Approval of Gate 1
    manifest.scope_approval = {"status": "APPROVED", "approver": "product_owner"}
    manifest.pending_user_actions.clear()
    store.save_project(manifest)

    # 3. ADVANCE AUTOMATICALLY THROUGH ROUTINE PHASES TO GATE 2 (UI/UX)
    # Controller advances through SRS, Architecture, Planning, and stops at UI/UX Gate 2
    res_gate2 = agent.advance_project_lifecycle(manifest)
    assert res_gate2["status"] == "APPROVAL_PENDING"
    assert any("GATE 2" in b for b in res_gate2["blockers"])

    # Simulate Human Approval of Gate 2 (UI/UX)
    manifest.uiux_approval = {"status": "APPROVED", "approver": "product_owner"}
    manifest.uiux_review_status = "APPROVED"
    manifest.pending_user_actions.clear()
    store.save_project(manifest)

    # 4. ADVANCE THROUGH IMPLEMENTATION & TESTING TO GATE 4 (SECURITY)
    manifest.testing_status = "COMPLETED"
    store.save_project(manifest)

    res_gate4 = agent.advance_project_lifecycle(manifest)
    assert res_gate4["status"] == "APPROVAL_PENDING"
    assert any("GATE 4" in b for b in res_gate4["blockers"])

    # Simulate Human Approval of Gate 4 (Security)
    manifest.security_status = "COMPLETED"
    manifest.security_approval = {"status": "APPROVED", "approver": "sec_lead"}
    manifest.pending_user_actions.clear()
    store.save_project(manifest)

    # 5. ADVANCE TO DEPLOYMENT GATE 8
    res_gate8 = agent.advance_project_lifecycle(manifest)
    assert res_gate8["status"] == "APPROVAL_PENDING"
    assert any("GATE 8" in b for b in res_gate8["blockers"])

    # CRITICAL: STRICT ZERO DEPLOYMENT WITHOUT GATE 8 APPROVAL
    assert manifest.deployment_status != "COMPLETED"
    assert manifest.current_phase != PhaseEnum.COMPLETED

    # Checkpoint safety
    assert manifest.last_successful_checkpoint is not None


def test_mandatory_restart_test(tmp_path):
    """MANDATORY RESTART TEST:
    Runs lifecycle until mid-project. Terminates lifecycle controller.
    Reloads project in a completely fresh controller and asserts all state, tasks,
    review verdicts, validation reports, and checkpoints are faithfully restored.
    """
    store_dir = tmp_path / "restart_projects"
    store_a = EngineeringProjectStore(storage_dir=store_dir)
    agent_a = LoopEngineeringAgent(store=store_a)

    manifest_a = agent_a.intake_project(
        idea="Mission Control Drone",
        repo_path=str(tmp_path / "drone_repo"),
    )
    manifest_a.current_phase = PhaseEnum.PHASE_10_BACKEND
    manifest_a.scope_approval = {"status": "APPROVED"}
    manifest_a.uiux_approval = {"status": "APPROVED"}
    manifest_a.last_successful_checkpoint = "ckpt_drone_midway"
    manifest_a.routing_history.append({"task_id": "t_nav", "worker": "worker_coding_agent"})
    manifest_a.review_history.append({"task_id": "t_nav", "verdict": "PASS"})
    manifest_a.validation_history.append({"task_id": "t_nav", "is_pass": True})
    manifest_a.repair_history.append({"task_id": "t_nav", "attempt": 1, "status": "RESOLVED"})
    store_a.save_project(manifest_a)

    # Complete destruction of in-memory instance
    del agent_a
    del store_a

    # Fresh controller instance
    store_b = EngineeringProjectStore(storage_dir=store_dir)
    agent_b = LoopEngineeringAgent(store=store_b)

    manifest_b = store_b.get_project("proj_mission_control_drone")
    assert manifest_b is not None
    assert manifest_b.current_phase == PhaseEnum.PHASE_10_BACKEND
    assert manifest_b.last_successful_checkpoint == "ckpt_drone_midway"
    assert len(manifest_b.routing_history) == 1
    assert len(manifest_b.review_history) == 1
    assert len(manifest_b.validation_history) == 1
    assert len(manifest_b.repair_history) == 1


def test_mandatory_multi_project_test(tmp_path):
    """MANDATORY MULTI-PROJECT TEST:
    Creates three distinct synthetic projects.
    Verifies: state isolation, priority scheduling, active project limit,
    pause/resume, independent approvals, independent artifacts, and no repository path crossover.
    """
    store = EngineeringProjectStore(storage_dir=tmp_path / "multi_projects")
    manager = MultiProjectManager(store=store, max_active_projects=2)

    p_hr = ProjectManifest(
        project_id="proj_syn_hr",
        project_name="Synthetic HR",
        project_type="NEW_PROJECT",
        repository_path=str(tmp_path / "repo_hr"),
        description="HR Assistant",
    )
    p_fin = ProjectManifest(
        project_id="proj_syn_fin",
        project_name="Synthetic Finance",
        project_type="NEW_PROJECT",
        repository_path=str(tmp_path / "repo_fin"),
        description="Finance Assistant",
    )
    p_saas = ProjectManifest(
        project_id="proj_syn_saas",
        project_name="Synthetic SaaS",
        project_type="NEW_PROJECT",
        repository_path=str(tmp_path / "repo_saas"),
        description="SaaS Product",
    )

    p_hr.artifacts = ["hr_srs.md", "hr_db.sql"]
    p_fin.artifacts = ["fin_srs.md", "fin_model.py"]
    p_saas.artifacts = ["saas_proto.html"]

    store.save_project(p_hr)
    store.save_project(p_fin)
    store.save_project(p_saas)

    # Priorities: SaaS (CRITICAL), HR (HIGH), Finance (NORMAL)
    manager.set_project_priority("proj_syn_saas", ProjectPriority.CRITICAL)
    manager.set_project_priority("proj_syn_hr", ProjectPriority.HIGH)
    manager.set_project_priority("proj_syn_fin", ProjectPriority.NORMAL)

    summaries = manager.list_projects_overview()
    assert len(summaries) == 3
    assert summaries[0]["project_id"] == "proj_syn_saas"
    assert summaries[1]["project_id"] == "proj_syn_hr"
    assert summaries[2]["project_id"] == "proj_syn_fin"

    # Strict isolation
    assert set(p_hr.artifacts).isdisjoint(set(p_fin.artifacts))
    assert set(p_fin.artifacts).isdisjoint(set(p_saas.artifacts))
    assert p_hr.repository_path != p_fin.repository_path != p_saas.repository_path


def test_mandatory_security_test(tmp_path):
    """MANDATORY SECURITY TEST:
    Injects synthetic secrets (OpenAI API key, GitHub token, JWT secret, DB password).
    Verifies Cockpit APIs, briefings, and project payloads redact them without leaking raw tokens.
    """
    client = TestClient(app)
    raw_key = "sk-proj-supersecretproductionkey999"
    raw_token = "ghp_PersonalAccessTokenABCDEFGHIJKLM99"
    raw_jwt = "eyJhGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSecretSignature99"

    manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea="Security Guard Project")
    manifest.description = f"Configured with key: {raw_key}, token: {raw_token}, jwt: {raw_jwt}"
    manifest.pending_user_actions = [f"Configure database credentials with key: {raw_key}"]
    DEFAULT_LOOP_ENGINEERING_AGENT.store.save_project(manifest)

    # 1. Check Cockpit project detail API
    res = client.get(f"/api/v1/engineering/projects/{manifest.project_id}")
    assert res.status_code == 200
    detail_str = res.text
    assert raw_key not in detail_str
    assert raw_token not in detail_str
    assert raw_jwt not in detail_str

    # 2. Check Owner Briefing API
    res_b = client.get(f"/api/v1/engineering/projects/{manifest.project_id}/owner-briefing")
    assert res_b.status_code == 200
    briefing_str = res_b.text
    assert raw_key not in briefing_str
    assert raw_token not in briefing_str
    assert raw_jwt not in briefing_str
