"""Repository Guard & Isolation Engine for ZERO Engineering Organization.

Enforces strict containment of all worker file reads, writes, and modifications
within the assigned project repository root, preventing:
- Directory traversal (`../`)
- Absolute paths escaping the repository boundary
- Cross-project file contamination
- Symlink escapes
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Tuple, Union

logger = logging.getLogger("zero.engineering.guard")


class RepositoryIsolationError(PermissionError):
    """Raised when an operation attempts to escape the project repository root."""
    pass


class RepositoryGuard:
    """Guards repository boundaries against unauthorized traversal and cross-project pollution."""

    @staticmethod
    def normalize_root(repo_root: Union[str, Path]) -> Path:
        """Resolves and normalizes repository root path."""
        root = Path(repo_root).resolve()
        return root

    @classmethod
    def is_safe_path(cls, repo_root: Union[str, Path], target_path: Union[str, Path]) -> bool:
        """Returns True if target_path resolves strictly within repo_root."""
        root = cls.normalize_root(repo_root)
        try:
            # Handle relative and absolute targets
            target = Path(target_path)
            if not target.is_absolute():
                resolved = (root / target).resolve()
            else:
                resolved = target.resolve()

            # Check if resolved path is relative to root
            return resolved == root or resolved.is_relative_to(root)
        except Exception:
            return False

    @classmethod
    def ensure_within_repository(
        cls,
        repo_root: Union[str, Path],
        target_path: Union[str, Path],
    ) -> Path:
        """Validates that target_path is within repo_root and returns resolved Path.
        
        Raises:
            RepositoryIsolationError if the path attempts to escape the repository.
        """
        root = cls.normalize_root(repo_root)
        target = Path(target_path)
        
        # Immediate check for suspicious traversal tokens
        str_target = str(target_path)
        if ".." in Path(str_target).parts:
            # Even if it resolves inside root (e.g. root/a/../b), flag if escaping root
            pass

        resolved = (root / target).resolve() if not target.is_absolute() else target.resolve()

        if not (resolved == root or resolved.is_relative_to(root)):
            msg = f"Security Violation: Target path '{target_path}' escapes repository boundary '{root}'"
            logger.error(msg)
            raise RepositoryIsolationError(msg)

        return resolved

    @classmethod
    def audit_affected_files(
        cls,
        repo_root: Union[str, Path],
        file_paths: List[str],
    ) -> Tuple[bool, List[str]]:
        """Audits a collection of file paths proposed by a worker.
        
        Returns:
            (is_safe, list_of_violations)
        """
        violations = []
        for fp in file_paths:
            if not cls.is_safe_path(repo_root, fp):
                violations.append(f"Repository boundary violation: '{fp}' escapes '{repo_root}'")
        return (len(violations) == 0), violations


DEFAULT_REPOSITORY_GUARD = RepositoryGuard()
