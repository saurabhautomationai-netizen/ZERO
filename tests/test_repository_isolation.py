"""Tests for Repository Guard & Isolation Engine (Phase 7).

Verifies strict containment of worker modifications within the assigned project
repository root and rejection of directory traversal, foreign absolute paths,
and cross-project escapes.
"""

import pytest
from pathlib import Path
from zero_core.engineering.repository_guard import (
    RepositoryGuard,
    RepositoryIsolationError,
    DEFAULT_REPOSITORY_GUARD,
)


def test_safe_repository_paths(tmp_path):
    repo_root = tmp_path / "my_project"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "main.py").write_text("# main", encoding="utf-8")

    guard = RepositoryGuard()

    # Relative safe paths
    assert guard.is_safe_path(repo_root, "src/main.py") is True
    assert guard.is_safe_path(repo_root, "docs/README.md") is True
    assert guard.is_safe_path(repo_root, "app.py") is True

    # Absolute path inside repo
    abs_inside = (repo_root / "src" / "main.py").resolve()
    assert guard.is_safe_path(repo_root, abs_inside) is True


def test_directory_traversal_rejection(tmp_path):
    repo_root = tmp_path / "my_project"
    repo_root.mkdir()

    guard = RepositoryGuard()

    # Attempts to escape with ../
    traversal_attempts = [
        "../sibling_project/secret.py",
        "../../etc/passwd",
        "src/../../outside.py",
        "..\\..\\Windows\\System32\\calc.exe",
    ]

    for attempt in traversal_attempts:
        assert guard.is_safe_path(repo_root, attempt) is False
        with pytest.raises(RepositoryIsolationError):
            guard.ensure_within_repository(repo_root, attempt)


def test_foreign_absolute_path_rejection(tmp_path):
    repo_root = tmp_path / "project_a"
    repo_root.mkdir()

    foreign_dir = tmp_path / "project_b"
    foreign_dir.mkdir()
    foreign_file = foreign_dir / "confidential.json"
    foreign_file.write_text("{}", encoding="utf-8")

    guard = RepositoryGuard()

    # Foreign absolute path
    assert guard.is_safe_path(repo_root, foreign_file) is False
    with pytest.raises(RepositoryIsolationError):
        guard.ensure_within_repository(repo_root, foreign_file)


def test_audit_affected_files_boundary_enforcement(tmp_path):
    repo_root = tmp_path / "isolated_repo"
    repo_root.mkdir()

    candidate_files = [
        "components/header.py",
        "ui/views/candidate.py",
        "../secrets/api_key.txt",  # Violation
        "docs/ARCHITECTURE.md",
    ]

    is_safe, violations = DEFAULT_REPOSITORY_GUARD.audit_affected_files(repo_root, candidate_files)
    assert is_safe is False
    assert len(violations) == 1
    assert "api_key.txt" in violations[0]
