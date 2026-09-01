"""Tests for State Corruption & Fault Tolerance Safety (Phase 7).

Verifies fail-safe handling when manifests or checkpoints are missing, corrupted,
stale, or referencing non-existent repositories. ZERO must fail safely and
never invent fictitious state or crash unexpectedly.
"""

import pytest
from pathlib import Path
from zero_core.engineering.checkpoints import CheckpointManager
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.engineering.manifest import ProjectManifest, PhaseEnum
from zero_core.engineering.multi_project import MultiProjectManager


def test_missing_manifest_handling(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    res = store.get_project("non_existent_project_id_123")
    assert res is None


def test_corrupted_json_manifest_handling(tmp_path):
    store_dir = tmp_path / "projects"
    store_dir.mkdir()
    corrupt_file = store_dir / "corrupted_project.json"
    corrupt_file.write_text("{ this is completely invalid json !!! }", encoding="utf-8")

    store = EngineeringProjectStore(storage_dir=store_dir)
    res = store.get_project("corrupted_project")
    # Must fail safely and return None without raising unhandled exception
    assert res is None


def test_missing_checkpoint_handling(tmp_path):
    ckpt_mgr = CheckpointManager(checkpoint_dir=tmp_path / "ckpts")
    res = ckpt_mgr.get_checkpoint("proj_test", "ckpt_missing_999")
    assert res is None

    restored = ckpt_mgr.restore_manifest_from_checkpoint("proj_test", "ckpt_missing_999")
    assert restored is None


def test_corrupted_checkpoint_file_handling(tmp_path):
    ckpt_dir = tmp_path / "ckpts" / "proj_corrupt"
    ckpt_dir.mkdir(parents=True)
    corrupt_ckpt = ckpt_dir / "ckpt_bad.json"
    corrupt_ckpt.write_text("NOT_JSON_DATA_AT_ALL", encoding="utf-8")

    ckpt_mgr = CheckpointManager(checkpoint_dir=tmp_path / "ckpts")
    res = ckpt_mgr.get_checkpoint("proj_corrupt", "ckpt_bad")
    assert res is None


def test_missing_or_moved_repository_handling(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    missing_repo = tmp_path / "ghost_directory"

    manifest = ProjectManifest(
        project_id="proj_ghost",
        project_name="Ghost Project",
        project_type="EXISTING_PROJECT",
        repository_path=str(missing_repo),
        description="Testing deleted repo safety",
    )
    store.save_project(manifest)

    manager = MultiProjectManager(store=store)
    briefing = manager.generate_owner_briefing("proj_ghost")
    # Must generate safe briefing without crashing
    assert briefing["project_id"] == "proj_ghost"
    assert "Ghost Project" in briefing["project_name"]
