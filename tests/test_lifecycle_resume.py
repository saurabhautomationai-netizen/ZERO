"""Tests for Process Restart and State Recovery in Project Lifecycle."""

import pytest
from zero_core.agents.loop_engineering import LoopEngineeringAgent
from zero_core.engineering.lifecycle import ProjectLifecycleController, TaskDAG, TaskState
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest
from zero_core.engineering.store import EngineeringProjectStore


def test_process_restart_restores_exact_lifecycle_state(tmp_path):
    store_dir = tmp_path / "projects"
    store1 = EngineeringProjectStore(storage_dir=store_dir)
    agent1 = LoopEngineeringAgent(store=store1)

    # 1. Create project and advance to Architecture phase
    manifest1 = agent1.intake_project(idea="State Recovery Service", repo_path=str(tmp_path / "repo"))
    manifest1.current_phase = PhaseEnum.PHASE_3_ARCHITECTURE
    manifest1.scope_approval = "APPROVED"
    manifest1.last_successful_checkpoint = "ckpt_arch_001"
    manifest1.routing_history.append({"task_type": "ARCHITECTURE", "worker": "worker_project_builder"})
    manifest1.review_history.append({"verdict": "PASS", "reviewer": "worker_chatgpt"})
    manifest1.validation_history.append({"is_pass": True, "syntax_valid": True})
    manifest1.repair_history.append({"attempt": 1, "status": "RESOLVED"})
    store1.save_project(manifest1)

    # 2. Simulate complete process restart (terminate agent1, instantiate agent2 with fresh memory)
    del agent1
    del store1

    store2 = EngineeringProjectStore(storage_dir=store_dir)
    agent2 = LoopEngineeringAgent(store=store2)

    # 3. Reload project from store
    manifest2 = store2.load_project("proj_state_recovery_service")
    assert manifest2 is not None

    # 4. Verify all state, history, and checkpoints restored without restarting
    assert manifest2.current_phase == PhaseEnum.PHASE_3_ARCHITECTURE
    assert manifest2.scope_approval == "APPROVED"
    assert manifest2.last_successful_checkpoint == "ckpt_arch_001"
    assert len(manifest2.routing_history) == 1
    assert len(manifest2.review_history) == 1
    assert len(manifest2.validation_history) == 1
    assert len(manifest2.repair_history) == 1
    assert manifest2.current_phase != PhaseEnum.PHASE_0_INTAKE
    assert manifest2.current_phase != PhaseEnum.PHASE_1_DISCOVERY

    # 5. Verify DAG reconstructed properly
    dag = agent2.lifecycle.get_or_create_dag(manifest2)
    assert dag is not None
