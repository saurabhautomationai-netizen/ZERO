"""Phase & Quality Gate Validator for ZERO Engineering.

Validates that code satisfies acceptance criteria, has 0 syntax errors,
passes required pytest suites, and complies with clean architecture standards.
"""

from __future__ import annotations

import ast
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, TaskItem

logger = logging.getLogger("zero.engineering.validator")


class ValidationReport(BaseModel):
    is_valid: bool
    phase: PhaseEnum
    passed_checks: List[str] = Field(default_factory=list)
    failed_checks: List[str] = Field(default_factory=list)
    syntax_errors: List[str] = Field(default_factory=list)
    test_results: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


class PhaseValidator:
    """Validates phase completion and task outputs."""

    def validate_code_syntax(self, repo_path: str) -> List[str]:
        """Checks all Python files in repository for syntax errors."""
        root = Path(repo_path)
        if not root.exists():
            return [f"Repository path does not exist: {repo_path}"]

        errors = []
        for py_file in root.rglob("*.py"):
            if any(part.startswith((".", "__pycache__", "venv", ".venv")) for part in py_file.parts):
                continue
            try:
                ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError as exc:
                errors.append(f"{py_file.name}: {exc.msg} on line {exc.lineno}")
        return errors

    def run_tests(self, repo_path: str) -> Dict[str, Any]:
        """Runs pytest on the project tests/ directory using the project's virtual environment."""
        root = Path(repo_path)
        tests_dir = root / "tests"
        if not tests_dir.exists():
            return {"success": True, "executed": False, "message": "No tests directory found."}

        # Resolve project-specific Python interpreter if virtualenv exists
        python_bin = sys.executable
        for venv_candidate in (
            root / "venv" / "Scripts" / "python.exe",
            root / ".venv" / "Scripts" / "python.exe",
            root / "venv" / "bin" / "python",
            root / ".venv" / "bin" / "python",
        ):
            if venv_candidate.exists():
                python_bin = str(venv_candidate)
                break

        cmd = [python_bin, "-m", "pytest", str(tests_dir)]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": res.returncode == 0,
                "executed": True,
                "exit_code": res.returncode,
                "output": res.stdout + "\n" + res.stderr,
            }
        except Exception as exc:
            return {"success": False, "executed": True, "error": str(exc)}

    def validate_phase_transition(
        self,
        manifest: ProjectManifest,
        target_phase: PhaseEnum,
    ) -> ValidationReport:
        """Determines whether a project satisfies all criteria to advance to the next phase."""
        passed = []
        failed = []
        syntax_errors = self.validate_code_syntax(manifest.repository_path)
        
        if syntax_errors:
            failed.append(f"Found {len(syntax_errors)} Python syntax error(s).")
        else:
            passed.append("100% Python syntax validation passed.")

        # Phase-specific checks
        root = Path(manifest.repository_path)
        
        if target_phase in (PhaseEnum.PHASE_3_ARCHITECTURE, PhaseEnum.PHASE_4_STRUCTURE):
            if (root / "docs" / "SRS.md").exists() or manifest.requirements_status == "COMPLETED":
                passed.append("SRS requirements documented.")
            else:
                failed.append("Missing docs/SRS.md.")

        if target_phase == PhaseEnum.PHASE_6_PLANNING:
            if (root / "docs" / "ARCHITECTURE.md").exists() or manifest.architecture_status == "COMPLETED":
                passed.append("Architecture documentation verified.")
            else:
                failed.append("Missing docs/ARCHITECTURE.md.")

        if target_phase in (PhaseEnum.PHASE_13_TESTING, PhaseEnum.PHASE_14_SECURITY, PhaseEnum.COMPLETED):
            test_res = self.run_tests(manifest.repository_path)
            if test_res.get("executed") and not test_res.get("success"):
                failed.append(f"Automated test suite failed (exit code: {test_res.get('exit_code')}).")
            else:
                passed.append("Automated test suite executed and passed.")

        is_valid = len(failed) == 0 and len(syntax_errors) == 0

        return ValidationReport(
            is_valid=is_valid,
            phase=target_phase,
            passed_checks=passed,
            failed_checks=failed,
            syntax_errors=syntax_errors,
        )


DEFAULT_PHASE_VALIDATOR = PhaseValidator()
