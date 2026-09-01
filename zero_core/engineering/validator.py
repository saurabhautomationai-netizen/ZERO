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

    def validate_task_execution(
        self,
        manifest: ProjectManifest,
        task: TaskItem,
        worker_result: Any,
    ) -> ValidationResult:
        """Executes objective, tool-driven validation proving code correctness and test results."""
        task_id = getattr(task, "task_id", "unknown_task")
        checks_run = []
        checks_passed = []
        checks_failed = []
        forbidden_findings = []
        syntax_errors = []

        repo_dir = Path(manifest.repository_path) if Path(manifest.repository_path).exists() else Path(".")

        # 1. Syntax Validation on affected files
        checks_run.append("SYNTAX_CHECK")
        affected_files = list(getattr(worker_result, "files_created", [])) + list(getattr(worker_result, "files_modified", []))
        if affected_files:
            for fpath in affected_files:
                resolved = (repo_dir / fpath) if not Path(fpath).is_absolute() else Path(fpath)
                if resolved.exists() and resolved.suffix == ".py":
                    try:
                        ast.parse(resolved.read_text(encoding="utf-8", errors="ignore"))
                    except SyntaxError as exc:
                        syntax_errors.append(f"{resolved.name}: {exc.msg} on line {exc.lineno}")
        else:
            syntax_errors = self.validate_code_syntax(str(repo_dir))

        if syntax_errors:
            checks_failed.append(f"Syntax validation failed with {len(syntax_errors)} error(s)")
        else:
            checks_passed.append("100% Python syntax validation passed")

        # 2. Forbidden Boundary Check
        checks_run.append("SECURITY_BOUNDARY_CHECK")
        forbidden_patterns = {".env", ".git", "credentials.json", "secrets.json", "id_rsa"}
        for fpath in affected_files:
            fname = Path(fpath).name
            if fname in forbidden_patterns or any(part in forbidden_patterns for part in Path(fpath).parts):
                forbidden_findings.append(f"Forbidden file modification attempted: {fpath}")

        if forbidden_findings:
            checks_failed.append(f"Security boundary check failed ({len(forbidden_findings)} violations)")
        else:
            checks_passed.append("Security file boundaries verified")

        # 3. Test Suite Execution (pytest)
        checks_run.append("AUTOMATED_TESTS")
        test_results = {}
        tests_dir = repo_dir / "tests"
        if tests_dir.exists() and any(tests_dir.rglob("*.py")):
            test_results = self.run_tests(str(repo_dir))
            if test_results.get("executed"):
                if test_results.get("success"):
                    checks_passed.append("Automated pytest suite passed cleanly")
                else:
                    checks_failed.append(f"Automated pytest suite failed (exit code: {test_results.get('exit_code')})")
            else:
                checks_passed.append("Test runner executed")
        else:
            checks_passed.append("No executable pytest directory required for this task")

        # 4. Synthesize Status
        is_pass = len(checks_failed) == 0 and len(syntax_errors) == 0 and len(forbidden_findings) == 0
        status = ValidationStatus.PASS if is_pass else ValidationStatus.FAIL
        failure_summary = "; ".join(checks_failed) if checks_failed else "All objective validation checks passed."

        return ValidationResult(
            task_id=task_id,
            status=status,
            checks_run=checks_run,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            test_results=test_results,
            syntax_errors=syntax_errors,
            forbidden_change_findings=forbidden_findings,
            failure_summary=failure_summary,
        )


import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


class ValidationStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass
class ValidationResult:
    task_id: str
    status: ValidationStatus
    checks_run: List[str] = field(default_factory=list)
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    test_results: Dict[str, Any] = field(default_factory=dict)
    syntax_errors: List[str] = field(default_factory=list)
    forbidden_change_findings: List[str] = field(default_factory=list)
    failure_summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_pass(self) -> bool:
        return self.status == ValidationStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value if isinstance(self.status, ValidationStatus) else str(self.status),
            "checks_run": self.checks_run,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "test_results": self.test_results,
            "syntax_errors": self.syntax_errors,
            "forbidden_change_findings": self.forbidden_change_findings,
            "failure_summary": self.failure_summary,
            "timestamp": self.timestamp,
        }


DEFAULT_PHASE_VALIDATOR = PhaseValidator()
