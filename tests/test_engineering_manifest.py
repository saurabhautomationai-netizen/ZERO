import tempfile
from pathlib import Path
import pytest
from zero_core.engineering.manifest import (
    PhaseEnum,
    ProjectManifest,
    ProjectStatus,
    TaskItem,
    TaskStatus,
)
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.engineering.checkpoints import CheckpointManager


def test_manifest_creation_and_progress_calculation():
    manifest = ProjectManifest(
        project_id="proj_test_manifest",
        project_name="Test Engineering Project",
        description="A test project for manifest testing",
        repository_path="f:/AI Automation/Projects/Test Project",
    )
    assert manifest.project_status == ProjectStatus.INTAKE
    assert manifest.current_phase == PhaseEnum.PHASE_0_INTAKE
    assert manifest.overall_progress == 0

    manifest.current_phase = PhaseEnum.PHASE_3_ARCHITECTURE
    assert manifest.calculate_progress() == 25

    manifest.current_phase = PhaseEnum.PHASE_11_FRONTEND
    assert manifest.calculate_progress() == 85

    manifest.current_phase = PhaseEnum.COMPLETED
    assert manifest.calculate_progress() == 100


def test_manifest_decisions_and_approvals():
    manifest = ProjectManifest(
        project_id="proj_decisions",
        project_name="Decision Test",
        description="Testing decisions log",
        repository_path="f:/AI Automation/Projects/Test",
    )
    manifest.record_decision("DATABASE", "PostgreSQL with pgvector", "Required for vector RAG")
    assert len(manifest.decision_history) == 1
    assert manifest.decision_history[0]["category"] == "DATABASE"

    manifest.record_approval("GATE_1_SCOPE", "admin", "APPROVED", "All features approved")
    assert len(manifest.approval_history) == 1
    assert manifest.approval_history[0]["status"] == "APPROVED"


def test_store_persistence_and_retrieval():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EngineeringProjectStore(storage_dir=Path(tmpdir))
        manifest = ProjectManifest(
            project_id="proj_store_test",
            project_name="Store Project",
            description="Persistent store test",
            repository_path=tmpdir,
        )
        store.save_project(manifest)

        retrieved = store.get_project("proj_store_test")
        assert retrieved is not None
        assert retrieved.project_name == "Store Project"

        by_name = store.find_by_name("Store Project")
        assert by_name is not None
        assert by_name.project_id == "proj_store_test"


def test_checkpoint_creation_and_restore():
    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt_mgr = CheckpointManager(checkpoint_dir=Path(tmpdir) / "checkpoints")
        manifest = ProjectManifest(
            project_id="proj_ckpt_test",
            project_name="Checkpoint Test",
            description="Testing checkpoint manager",
            repository_path=tmpdir,
            current_phase=PhaseEnum.PHASE_5_UIUX,
        )
        ckpt = ckpt_mgr.create_checkpoint(manifest, "Phase 5 checkpoint")
        assert ckpt.checkpoint_id.startswith("ckpt_")
        assert ckpt.phase == PhaseEnum.PHASE_5_UIUX

        restored = ckpt_mgr.restore_manifest_from_checkpoint("proj_ckpt_test", ckpt.checkpoint_id)
        assert restored is not None
        assert restored.project_id == "proj_ckpt_test"
        assert restored.current_phase == PhaseEnum.PHASE_5_UIUX
