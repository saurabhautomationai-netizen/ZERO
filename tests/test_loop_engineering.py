import tempfile
from pathlib import Path
import pytest
from zero_core.agents.loop_engineering import LoopEngineeringAgent
from zero_core.engineering.checkpoints import CheckpointManager
from zero_core.engineering.manifest import PhaseEnum, ProjectStatus
from zero_core.engineering.store import EngineeringProjectStore


def test_loop_engineering_intake_and_discovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EngineeringProjectStore(storage_dir=Path(tmpdir) / "manifests")
        ckpts = CheckpointManager(checkpoint_dir=Path(tmpdir) / "ckpts")
        agent = LoopEngineeringAgent(store=store, checkpoints=ckpts)

        manifest = agent.intake_project(
            idea="Build an autonomous HR Recruitment AI Assistant",
            name="HR Recruitment AI",
            target_dir=str(Path(tmpdir) / "hr_recruitment"),
        )
        assert manifest.project_name == "HR Recruitment AI"
        assert manifest.project_id == "proj_hr_recruitment_ai"

        discovery = agent.run_discovery(manifest)
        assert discovery["status"] == "APPROVAL_PENDING"
        assert discovery["gate"] == "FEATURE_SCOPE"
        assert len(discovery["feature_scope"]["must_have"]) > 0


def test_loop_engineering_full_approval_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = EngineeringProjectStore(storage_dir=Path(tmpdir) / "manifests")
        ckpts = CheckpointManager(checkpoint_dir=Path(tmpdir) / "ckpts")
        agent = LoopEngineeringAgent(store=store, checkpoints=ckpts)

        # 1. Intake
        manifest = agent.intake_project(
            idea="Build an AI Meeting Summarizer",
            name="Meeting Summarizer",
            target_dir=str(Path(tmpdir) / "meeting_summarizer"),
        )
        agent.run_discovery(manifest)

        # 2. Gate 1: Approve Scope -> executes SRS, Architecture, UI/UX
        res_gate1 = agent.approve_feature_scope(manifest.project_id)
        assert res_gate1["status"] == "APPROVAL_PENDING"
        assert res_gate1["gate"] == "UI_UX_DESIGN"
        assert (Path(manifest.repository_path) / "docs" / "SRS.md").exists()
        assert (Path(manifest.repository_path) / "docs" / "ARCHITECTURE.md").exists()

        # 3. Gate 2: Approve UI/UX -> executes Implementation & Testing -> stops at Security
        res_gate2 = agent.approve_uiux_and_build(manifest.project_id)
        assert res_gate2["status"] == "APPROVAL_PENDING"
        assert res_gate2["gate"] == "SECURITY_PERMISSIONS"
        assert res_gate2["database_status"] == "COMPLETED"
        assert res_gate2["backend_status"] == "COMPLETED"
        assert res_gate2["frontend_status"] == "COMPLETED"

        # 4. Gate 3 & 5: Approve Security & Deploy -> marks COMPLETED
        res_gate3 = agent.approve_security_and_deploy(manifest.project_id)
        assert res_gate3["status"] == "COMPLETED"
        assert res_gate3["progress"] == 100

        # 5. Check Summary
        summary = agent.get_project_summary("Meeting Summarizer")
        assert "Engineering Project: Meeting Summarizer [COMPLETED]" in summary
        assert "Last Checkpoint" in summary
