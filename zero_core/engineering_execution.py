"""G2A injected process boundary. No process implementation or approval authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol, Literal
import os
import stat

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, PermissionDecision, TaskPacket,
    WorkspacePolicy, utc_now,
)


def canonical_path(value: str, *, directory: bool) -> str:
    """Reject aliases/reparse points rather than silently following them.

    This is a planning-time check, not race-free OS containment.
    """
    if os.name not in ("nt", "posix"):
        raise ValueError("unsupported platform")
    path = Path(value)
    if not value or not path.is_absolute() or value.startswith(("//", "\\\\")):
        raise ValueError("absolute local path required")
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("ambiguous link or reparse point")
    resolved = path.resolve(strict=True)
    if path != resolved or (not resolved.is_dir() if directory else not resolved.is_file()):
        raise ValueError("invalid canonical path")
    if not directory:
        if os.name == "nt" and resolved.suffix.lower() != ".exe":
            raise ValueError("native executable required")
        if os.name == "posix" and not os.access(resolved, os.X_OK):
            raise ValueError("executable permission required")
    return resolved.as_posix()


def explicit_environment(values: Mapping[str, str]) -> Mapping[str, str]:
    # Closed, non-secret configuration vocabulary; never consult os.environ.
    allowed = {"CODEX_HOME", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG"}
    copied = dict(values)
    for key, value in copied.items():
        if key not in allowed or not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
            raise ValueError("unsupported environment entry")
        if key == "LANG":
            if value not in ("C", "C.UTF-8", "en_US.UTF-8"):
                raise ValueError("unsupported locale")
        else:
            canonical_path(value, directory=True)
    return MappingProxyType(copied)


@dataclass(frozen=True)
class TrustedAdapterConfiguration:
    project_id: str
    repository_root: str
    executable: str
    environment: Mapping[str, str]

    def __post_init__(self):
        if not self.project_id:
            raise ValueError("project required")
        object.__setattr__(self, "repository_root", canonical_path(self.repository_root, directory=True))
        object.__setattr__(self, "executable", canonical_path(self.executable, directory=False))
        object.__setattr__(self, "environment", explicit_environment(self.environment))

    def validate_binding(self, packet: TaskPacket, policy: WorkspacePolicy) -> None:
        root = canonical_path(self.repository_root, directory=True)
        canonical_path(self.executable, directory=False)
        explicit_environment(self.environment)
        if any((record.project_id, record.repository_root) != (self.project_id, root)
               for record in (packet, policy)):
            raise ValueError("trusted workspace mismatch")


@dataclass(frozen=True)
class ProcessInvocation:
    """Future runner MUST use shell=False and env exactly as supplied.

    Limits are requests only in G2A. No shell-string or inheritance option exists.
    """
    argv: tuple[str, ...]
    stdin: str
    cwd: str
    environment: Mapping[str, str]
    timeout_seconds: int = 60
    stdout_limit_bytes: int = 65536
    stderr_limit_bytes: int = 4096

    def __post_init__(self):
        if type(self.argv) is not tuple or not self.argv or any(
            not isinstance(arg, str) or not arg or "\x00" in arg for arg in self.argv
        ):
            raise ValueError("exact argv tuple required")
        canonical_path(self.argv[0], directory=False)
        if canonical_path(self.cwd, directory=True) != self.cwd:
            raise ValueError("canonical cwd required")
        if not isinstance(self.stdin, str) or "\x00" in self.stdin:
            raise ValueError("text stdin required")
        for value in (self.timeout_seconds, self.stdout_limit_bytes, self.stderr_limit_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError("positive integer request required")
        object.__setattr__(self, "environment", explicit_environment(self.environment))


@dataclass(frozen=True)
class ProcessOutcome:
    state: Literal["EXITED", "TIMEOUT", "CANCELLED", "MISSING_EXECUTABLE"]
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def __post_init__(self):
        if self.state not in ("EXITED", "TIMEOUT", "CANCELLED", "MISSING_EXECUTABLE"):
            raise ValueError("unknown process state")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ValueError("integer exit code required")
        for value in (self.started_at, self.finished_at):
            if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
                raise ValueError("UTC timestamp required")
        for text, limit in ((self.stdout, 65536), (self.stderr, 4096)):
            if not isinstance(text, str) or len(text) > limit:
                raise ValueError("bounded text required")
        if type(self.stdout_truncated) is not bool or type(self.stderr_truncated) is not bool:
            raise ValueError("boolean truncation flags required")
        if (self.state == "EXITED") != (self.exit_code is not None):
            raise ValueError("exit code/state mismatch")
        if self.finished_at < self.started_at:
            raise ValueError("nonmonotonic outcome")

    def model_copy(self, *, update):
        return replace(self, **update)

    @classmethod
    def model_validate(cls, value):
        if type(value) is not cls:
            raise ValueError("ProcessOutcome required")
        return replace(value)


class ProcessRunner(Protocol):
    def run(self, invocation: ProcessInvocation) -> ProcessOutcome: ...


class StatelessAdapter(Protocol):
    executor_id: str
    configuration: TrustedAdapterConfiguration

    def plan(self, packet: TaskPacket) -> ProcessInvocation: ...

    def parse(self, output: str) -> bool:
        """Return only reported success; reject unknown output with ValueError."""
        ...


def execute_attempt(packet: TaskPacket, policy: WorkspacePolicy,
                    decision: PermissionDecision, adapter: StatelessAdapter,
                    runner: ProcessRunner, *, execution_id: str) -> EngineeringExecutionResult:
    """Only validated LOW_RISK may cross the injected runner boundary."""
    packet = TaskPacket.model_validate(packet)
    started = utc_now()

    def result(status, summary, outcome=None):
        record = EngineeringExecutionResult(
            execution_id=execution_id, executor_id=adapter.executor_id,
            project_id=packet.project_id, task_id=packet.task_id,
            packet_fingerprint=packet.fingerprint(), permission_decision_id=decision.decision_id,
            status=status, summary=summary[:200],
            started_at=outcome.started_at if outcome else started,
            finished_at=outcome.finished_at if outcome else utc_now(),
        )
        return record

    try:
        decision.validate_binding(packet, policy)
        if not decision.permits_unattended_execution(packet, policy):
            return result("BLOCKED", "Unattended permission not granted.")
        adapter.configuration.validate_binding(packet, policy)
        invocation = adapter.plan(packet)
        config = adapter.configuration
        if (invocation.argv[0], invocation.cwd, dict(invocation.environment)) != (
            config.executable, config.repository_root, dict(config.environment)
        ):
            raise ValueError("invocation configuration mismatch")
    except (ValueError, OSError):
        # Never include external exceptions, paths, credentials or raw output.
        return result("BLOCKED", "Binding or adapter capability unsupported.")
    try:
        outcome = ProcessOutcome.model_validate(runner.run(invocation))
    except Exception:
        return result("FAILED", "Runner failed; external details withheld.")
    if outcome.state != "EXITED":
        status = {"TIMEOUT": "TIMEOUT", "CANCELLED": "CANCELLED",
                  "MISSING_EXECUTABLE": "BLOCKED"}[outcome.state]
        return result(status, "Process did not complete; attempt unverified.", outcome)
    if outcome.exit_code != 0:
        return result("FAILED", "Process reported a nonzero exit; details withheld.", outcome)
    if (outcome.stdout_truncated or outcome.stderr_truncated
            or len(outcome.stdout.encode("utf-8")) > invocation.stdout_limit_bytes
            or len(outcome.stderr.encode("utf-8")) > invocation.stderr_limit_bytes):
        return result("FAILED", "Incomplete or oversized output rejected.", outcome)
    try:
        success = adapter.parse(outcome.stdout)
        if type(success) is not bool:
            raise ValueError("invalid parser result")
    except Exception:
        return result("FAILED", "Unrecognized external output rejected.", outcome)
    record = result("SUCCESS" if success else "FAILED",
                    "Executor reported success; unverified." if success else "Executor reported failure.", outcome)
    record.validate_binding(packet, decision, policy)
    return record
