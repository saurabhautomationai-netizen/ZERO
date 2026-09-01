"""Tests for Human-in-the-Loop (HITL) gate enforcement within project lifecycles."""

import pytest
from zero_core.agents.loop_engineering import LoopEngineeringAgent
from zero_core.engineering.lifecycle import ProjectLifecycleController
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest
from zero_core.engineering.store import EngineeringProjectStore


def test_hitl_gate_stops_and_approval_advances(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    agent = LoopEngineeringAgent(store=store)

    manifest = agent.intake_project(idea="Automated Billing Microservice", repo_path=str(tmp_path))
    manifest.current_phase = PhaseEnum.PHASE_1_DISCOVERY

    # 1. Advance lifecycle -> stops at Gate 1 (Feature Scope)
    res = agent.advance_project_lifecycle(manifest)
    assert res["status"] == "APPROVAL_PENDING"
    assert any("GATE 1" in b for b in res["blockers"])
    assert len(manifest.pending_user_actions) > 0

    # 2. Approve Gate 1 (Feature Scope)
    manifest.scope_approval = "APPROVED"
    manifest.pending_user_actions.clear()
    store.save_project(manifest)

    # 3. Advance lifecycle -> automatically enters and advances through routine phases until next gate
    res_after = agent.advance_project_lifecycle(manifest)
    assert res_after["status"] in ("APPROVAL_PENDING", "COMPLETED")
    # Gate 1 should no longer be the blocker
    blockers = res_after.get("blockers", [])
    assert not any("GATE 1" in b for b in blockers)


def test_gate_8_production_deployment_strict_enforcement(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    agent = LoopEngineeringAgent(store=store)

    manifest = agent.intake_project(idea="Mission Critical Service", repo_path=str(tmp_path))
    manifest.current_phase = PhaseEnum.PHASE_17_DEPLOYMENT
    manifest.security_status = "COMPLETED"
    manifest.testing_status = "COMPLETED"
    manifest.deployment_status = "PENDING"  # No Gate 8 approval granted yet

    # Should not complete project without Gate 8 approval
    can_exit, reasons = agent.lifecycle.check_phase_exit(manifest, PhaseEnum.PHASE_17_DEPLOYMENT)
    assert can_exit is False
    assert any("GATE 8" in r for r in reasons)

    # Verify project cannot be marked COMPLETED prematurely
    can_complete, complete_reasons = agent.lifecycle.check_phase_entry(manifest, PhaseEnum.COMPLETED)
    assert can_complete is False
    assert any("deployment" in r.lower() for r in complete_reasons)
