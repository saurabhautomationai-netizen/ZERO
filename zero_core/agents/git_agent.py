"""Git Agent for ZERO (Milestone M16 & Autonomous Builder Pipeline).

Provides Git status inspection, conventional commit generation, repository initialization,
and destructive command guardrails.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# Block dangerous commands unless explicitly confirmed via approval system
DESTRUCTIVE_PATTERNS = [
    re.compile(r"git\s+push\s+.*--force", re.IGNORECASE),
    re.compile(r"git\s+reset\s+--hard", re.IGNORECASE),
    re.compile(r"git\s+clean\s+-fd", re.IGNORECASE),
    re.compile(r"git\s+branch\s+-D", re.IGNORECASE),
]


@dataclass
class GitStatusSummary:
    """Represents a clean summary of repository working tree state."""
    branch: str
    staged_files: List[str] = field(default_factory=list)
    unstaged_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    is_clean: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = [f"On branch: `{self.branch}`"]
        if self.is_clean:
            lines.append("Working tree is clean.")
        else:
            if self.staged_files:
                lines.append(f"Changes to be committed ({len(self.staged_files)}):")
                for f in self.staged_files:
                    lines.append(f"  + [staged] {f}")
            if self.unstaged_files:
                lines.append(f"Changes not staged ({len(self.unstaged_files)}):")
                for f in self.unstaged_files:
                    lines.append(f"  * [modified] {f}")
            if self.untracked_files:
                lines.append(f"Untracked files ({len(self.untracked_files)}):")
                for f in self.untracked_files:
                    lines.append(f"  ? [untracked] {f}")
        return "\n".join(lines)


class GitAgent:
    """Native Git Agent managing Git workflows and enforcing safety guardrails."""

    def is_operation_safe(self, command: str) -> bool:
        """Checks whether a Git command is safe or destructive."""
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern.search(command):
                return False
        return True

    def generate_conventional_commit(self, change_type: str, scope: str, description: str) -> str:
        """Generates a Conventional Commits formatted message."""
        valid_types = {"feat", "fix", "docs", "style", "refactor", "test", "chore", "perf"}
        ctype = change_type.lower() if change_type.lower() in valid_types else "chore"
        clean_desc = description.strip().rstrip(".")
        return f"{ctype}({scope}): {clean_desc}"

    def inspect_status(self, branch: str = "main", mock_changes: Optional[Dict[str, List[str]]] = None) -> GitStatusSummary:
        """Returns working tree status."""
        changes = mock_changes or {}
        staged = changes.get("staged", [])
        unstaged = changes.get("unstaged", [])
        untracked = changes.get("untracked", [])
        is_clean = len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0

        return GitStatusSummary(
            branch=branch,
            staged_files=staged,
            unstaged_files=unstaged,
            untracked_files=untracked,
            is_clean=is_clean,
        )

    def init_and_commit(self, repo_path: Path, message: str) -> Dict[str, Any]:
        """Initializes git repo if needed, stages all files, and creates a commit."""
        if not repo_path.exists():
            return {"success": False, "error": f"Path {repo_path} does not exist"}

        try:
            if not (repo_path / ".git").exists():
                subprocess.run(["git", "init"], cwd=str(repo_path), capture_output=True, check=True)

            subprocess.run(["git", "add", "."], cwd=str(repo_path), capture_output=True, check=True)
            res = subprocess.run(["git", "commit", "-m", message], cwd=str(repo_path), capture_output=True, text=True)
            return {
                "success": res.returncode == 0,
                "message": message,
                "output": res.stdout or res.stderr,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# Global singleton instance
DEFAULT_GIT_AGENT = GitAgent()
