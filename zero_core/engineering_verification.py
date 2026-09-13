"""ZERO-owned local observation boundary. No execution claims become evidence.

Fingerprints are unsigned integrity digests. No persistence or approval authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Protocol

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, PermissionDecision, TaskPacket, WorkspacePolicy,
    _relative_path,
)
from zero_core.engineering_execution import ProcessInvocation, ProcessOutcome, ProcessRunner, canonical_path


class VerificationVerdict(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationError(ValueError):
    """Fixed-code rejection before a bound evidence record can be constructed."""
    verdict = VerificationVerdict.BLOCKED

    def __init__(self, code="INVALID_CONFIGURATION"):
        if code not in {"INVALID_CONFIGURATION", "BINDING_INVALID", "OBSERVATION_LIMIT", "UNTRUSTED_PATH"}:
            code = "INVALID_CONFIGURATION"
        super().__init__(code)


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise VerificationError()


def _time(value):
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise VerificationError()


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise VerificationError()


def _paths(values):
    if type(values) is not tuple:
        raise VerificationError()
    for path in values:
        try:
            _relative_path(path)
        except (ValueError, TypeError, AttributeError):
            raise VerificationError("UNTRUSTED_PATH") from None
        if len(path) > 1024:
            raise VerificationError()
    if len(set(p.casefold() for p in values)) != len(values):
        raise VerificationError("UNTRUSTED_PATH")
    return tuple(sorted(values))


def _payload(value):
    if isinstance(value, Record):
        value.__post_init__()
        return {f.name: _payload(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        _time(value)
        return value.isoformat()
    if type(value) is tuple:
        return [_payload(v) for v in value]
    if type(value) in (str, int, bool) or value is None:
        return value
    raise VerificationError()


class Record:
    def canonical_json(self):
        return json.dumps(_payload(self), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

    def fingerprint(self):
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExpectedChange(Record):
    path: str
    kind: str

    def __post_init__(self):
        _paths((self.path,))
        if self.kind not in ("CREATED", "MODIFIED", "DELETED"):
            raise VerificationError()


@dataclass(frozen=True)
class VerificationCommand:
    """Trusted command definition; never serialized into evidence."""
    command_id: str
    invocation: ProcessInvocation

    def __post_init__(self):
        _id(self.command_id)
        if type(self.invocation) is not ProcessInvocation:
            raise VerificationError()
        object.__setattr__(self, "invocation", replace(self.invocation))

    def fingerprint(self):
        invocation = self.invocation
        data = {f.name: getattr(invocation, f.name) for f in fields(invocation)}
        data["environment"] = dict(invocation.environment)
        data["command_id"] = self.command_id
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class TrustedVerificationConfiguration:
    project_id: str
    task_id: str
    execution_id: str
    repository_root: str
    allowed_paths: tuple[str, ...]
    expected_changes: tuple[ExpectedChange, ...]
    commands: tuple[VerificationCommand, ...] = ()
    allow_deletions: bool = False
    max_files: int = 256
    max_file_bytes: int = 1048576
    max_evidence_bytes: int = 262144
    max_snapshot_bytes: int = 131072
    max_output_bytes: int = 4096

    def __post_init__(self):
        for value in (self.project_id, self.task_id, self.execution_id):
            _id(value)
        try:
            root = canonical_path(self.repository_root, directory=True)
        except (ValueError, OSError):
            raise VerificationError("UNTRUSTED_PATH") from None
        object.__setattr__(self, "repository_root", root)
        if len(root) > 1024:
            raise VerificationError()
        object.__setattr__(self, "allowed_paths", _paths(self.allowed_paths))
        if type(self.expected_changes) is not tuple or type(self.commands) is not tuple:
            raise VerificationError()
        if not self.expected_changes and not self.commands:
            raise VerificationError()
        for change in self.expected_changes:
            if type(change) is not ExpectedChange or change.path not in self.allowed_paths:
                raise VerificationError()
            change.__post_init__()
        _paths(tuple(c.path for c in self.expected_changes))
        object.__setattr__(self, "expected_changes", tuple(sorted(self.expected_changes, key=lambda x: x.path)))
        if any(type(c) is not VerificationCommand for c in self.commands):
            raise VerificationError()
        if len(self.commands) > 32 or len({c.command_id for c in self.commands}) != len(self.commands):
            raise VerificationError()
        for command in self.commands:
            if type(command) is not VerificationCommand or command.invocation.cwd != root:
                raise VerificationError()
            command.__post_init__()
        if type(self.allow_deletions) is not bool:
            raise VerificationError()
        for value, cap in ((self.max_files, 10000), (self.max_file_bytes, 67108864),
                           (self.max_evidence_bytes, 4194304), (self.max_snapshot_bytes, 2097152),
                           (self.max_output_bytes, 65536)):
            if type(value) is not int or not 1 <= value <= cap:
                raise VerificationError()
        if self.max_evidence_bytes < 4096 or len(self.allowed_paths) > self.max_files:
            raise VerificationError()

    def fingerprint(self):
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["expected_changes"] = [_payload(v) for v in self.expected_changes]
        data["commands"] = [v.fingerprint() for v in self.commands]
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class Binding(Record):
    project_id: str
    task_id: str
    execution_id: str
    repository_root: str
    packet_digest: str
    policy_digest: str
    decision_digest: str
    configuration_digest: str

    def __post_init__(self):
        for value in (self.project_id, self.task_id, self.execution_id):
            _id(value)
        # Lexical validation through G1, without filesystem reads in evidence.
        from zero_core.engineering_contracts import _root
        _root(self.repository_root)
        for value in (self.packet_digest, self.policy_digest, self.decision_digest, self.configuration_digest):
            _digest(value)


@dataclass(frozen=True)
class FileObservation(Record):
    path: str
    state: str
    file_type: str
    size: int = 0
    content_digest: str | None = None
    metadata: tuple[int, ...] = ()

    def __post_init__(self):
        _paths((self.path,))
        if self.state not in ("PRESENT", "ABSENT", "BLOCKED", "UNAVAILABLE", "RACE"):
            raise VerificationError()
        if self.file_type not in ("REGULAR", "DIRECTORY", "SPECIAL", "UNKNOWN"):
            raise VerificationError()
        if type(self.size) is not int or self.size < 0 or type(self.metadata) is not tuple:
            raise VerificationError()
        if len(self.metadata) > 6 or any(type(v) is not int for v in self.metadata):
            raise VerificationError()
        if self.content_digest is not None:
            _digest(self.content_digest)
        if (self.state == "PRESENT" and self.file_type == "REGULAR") != (self.content_digest is not None):
            raise VerificationError()


@dataclass(frozen=True)
class WorkspaceSnapshot(Record):
    binding: Binding
    phase: str
    observed_at: datetime
    entries: tuple[FileObservation, ...]
    issues: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.binding) is not Binding or self.phase not in ("PRE", "POST") or type(self.entries) is not tuple:
            raise VerificationError()
        self.binding.__post_init__()
        _time(self.observed_at)
        for entry in self.entries:
            if type(entry) is not FileObservation:
                raise VerificationError()
            entry.__post_init__()
        _paths(tuple(entry.path for entry in self.entries))
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda e: e.path)))
        if type(self.issues) is not tuple or any(v not in ("LIMIT", "UNTRUSTED", "RACE", "UNAVAILABLE") for v in self.issues):
            raise VerificationError()
        object.__setattr__(self, "issues", tuple(sorted(set(self.issues))))


@dataclass(frozen=True)
class ChangeObservation(Record):
    created: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()

    def __post_init__(self):
        for field in fields(self):
            object.__setattr__(self, field.name, _paths(getattr(self, field.name)))
        _paths(self.created + self.modified + self.deleted + self.unchanged)


@dataclass(frozen=True)
class TestEvidence(Record):
    command_id: str
    command_digest: str
    state: str
    exit_code: int | None
    stdout_digest: str | None
    stderr_digest: str | None
    stdout_truncated: bool
    stderr_truncated: bool
    started_at: datetime
    finished_at: datetime
    verdict: VerificationVerdict
    reason: str
    summary: str = field(init=False)

    def __post_init__(self):
        _id(self.command_id)
        _digest(self.command_digest)
        for value in (self.stdout_digest, self.stderr_digest):
            if value is not None:
                _digest(value)
        if self.state not in ("EXITED", "TIMEOUT", "CANCELLED", "MISSING_EXECUTABLE", "RUNNER_ERROR"):
            raise VerificationError()
        if (self.state == "EXITED") != (self.exit_code is not None) or (self.exit_code is not None and type(self.exit_code) is not int):
            raise VerificationError()
        _time(self.started_at)
        _time(self.finished_at)
        if self.finished_at < self.started_at or type(self.verdict) is not VerificationVerdict:
            raise VerificationError()
        if type(self.stdout_truncated) is not bool or type(self.stderr_truncated) is not bool:
            raise VerificationError()
        if self.reason not in ("EXIT_ZERO_UNVERIFIED_TASK", "NONZERO_EXIT", "INCOMPLETE_OUTPUT", "PROCESS_INCOMPLETE", "RUNNER_FAILURE"):
            raise VerificationError()
        object.__setattr__(self, "summary", {
            "EXIT_ZERO_UNVERIFIED_TASK": "Approved command exited zero; task completion not established.",
            "NONZERO_EXIT": "Approved command exited nonzero.",
            "INCOMPLETE_OUTPUT": "Output was truncated or exceeded an evidence limit.",
            "PROCESS_INCOMPLETE": "Command did not complete normally.",
            "RUNNER_FAILURE": "Runner failed; external details withheld.",
        }[self.reason])
        if self.verdict == VerificationVerdict.VERIFIED and (
            self.state != "EXITED" or self.exit_code != 0 or self.stdout_truncated or self.stderr_truncated
            or self.stdout_digest is None or self.stderr_digest is None
        ):
            raise VerificationError()


@dataclass(frozen=True)
class VerificationEvidence(Record):
    binding: Binding
    execution_digest: str
    pre_digest: str
    post_digest: str
    changes: ChangeObservation
    tests: tuple[TestEvidence, ...]
    verdict: VerificationVerdict
    reason_codes: tuple[str, ...]
    created_at: datetime
    schema_version: int = 1
    fingerprint_kind: str = "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1 or self.fingerprint_kind != "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED":
            raise VerificationError()
        if type(self.binding) is not Binding or type(self.changes) is not ChangeObservation:
            raise VerificationError()
        for value in (self.execution_digest, self.pre_digest, self.post_digest):
            _digest(value)
        if type(self.tests) is not tuple or any(type(t) is not TestEvidence for t in self.tests):
            raise VerificationError()
        if len({t.command_id for t in self.tests}) != len(self.tests):
            raise VerificationError()
        if type(self.verdict) is not VerificationVerdict or type(self.reason_codes) is not tuple or not self.reason_codes:
            raise VerificationError()
        allowed = {"OBSERVED_REQUIREMENTS_MET", "BINDING_INVALID", "COMMAND_NOT_APPROVED", "OBSERVATION_BLOCKED",
                   "OBSERVATION_UNCERTAIN", "UNEXPECTED_CHANGE", "DELETION_PROHIBITED", "EXPECTED_CHANGE_MISSING",
                   "TEST_NOT_PASSED", "TEST_MUTATED_WORKSPACE", "EVIDENCE_LIMIT"}
        if any(code not in allowed for code in self.reason_codes):
            raise VerificationError()
        if self.verdict == VerificationVerdict.VERIFIED and (
            self.changes.unexpected or self.changes.unsupported
            or any(t.verdict != VerificationVerdict.VERIFIED for t in self.tests)
            or self.reason_codes != ("OBSERVED_REQUIREMENTS_MET",)
        ):
            raise VerificationError()
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        _time(self.created_at)


class Clock(Protocol):
    def now(self) -> datetime: ...


class WorkspaceObserver(Protocol):
    def observe(self, configuration: TrustedVerificationConfiguration, binding: Binding,
                phase: str, observed_at: datetime) -> WorkspaceSnapshot: ...


def _metadata(info):
    # Windows ctime has differing creation/change semantics across stat APIs.
    # Birth time is explicitly named and agrees between path and handle queries.
    created_or_changed = info.st_birthtime_ns if os.name == "nt" else info.st_ctime_ns
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, created_or_changed)


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _chain(root: Path, path: Path):
    canonical_path(root.as_posix(), directory=True)
    path.relative_to(root)
    result = []
    for parent in (root, *reversed(path.relative_to(root).parents)):
        if parent == Path("."):
            continue
        full = parent if parent.is_absolute() else root / parent
        info = full.lstat()
        if _link(info) or not stat.S_ISDIR(info.st_mode):
            raise VerificationError("UNTRUSTED_PATH")
        result.append((full.as_posix(), info.st_dev, info.st_ino))
    return tuple(result)


def _open_regular(root: Path, path: Path):
    """Open without following a final link; establish handle containment first."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x00200000 | 0x08000000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError("OBSERVATION_UNAVAILABLE")
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
            if not 0 < length < len(buffer):
                raise VerificationError("UNTRUSTED_PATH")
            actual = buffer.value
            if actual.startswith("\\\\?\\"):
                actual = actual[4:]
            if Path(actual) != path:
                raise VerificationError("UNTRUSTED_PATH")
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            handle = None
            return os.fdopen(fd, "rb", buffering=0)
        finally:
            if handle is not None:
                api.CloseHandle(handle)
    if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = path.relative_to(root).parts
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            return os.fdopen(fd, "rb", buffering=0)
        finally:
            os.close(directory)
    raise VerificationError("UNTRUSTED_PATH")


@contextmanager
def _directory_entries(root, directory):
    """Pin the directory without following links while enumerating its names."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Attributes(ctypes.Structure):
            _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.GetFileInformationByHandleEx.restype = wintypes.BOOL
        api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.CreateFileW(str(directory), 0x80000000, 1, None, 3, 0x02000000 | 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise VerificationError("UNTRUSTED_PATH")
        try:
            info = Attributes()
            if not api.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise VerificationError("UNTRUSTED_PATH")
            if info.attributes & 0x400 or not info.attributes & 0x10:
                raise VerificationError("UNTRUSTED_PATH")
            buffer = ctypes.create_unicode_buffer(32768)
            length = api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
            if not 0 < length < len(buffer) or Path(buffer.value.removeprefix("\\\\?\\")) != directory:
                raise VerificationError("UNTRUSTED_PATH")
            with os.scandir(directory) as iterator:
                yield iterator
        finally:
            if not api.CloseHandle(handle):
                raise VerificationError("UNTRUSTED_PATH")
    elif os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in directory.relative_to(root).parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            with os.scandir(descriptor) as iterator:
                yield iterator
        finally:
            os.close(descriptor)
    else:
        raise VerificationError("UNTRUSTED_PATH")


class LocalWorkspaceObserver:
    """Bounded shallow inventory; recurse only into ancestors of trusted paths.

    Unapproved files get metadata only; opaque branches are never traversed.
    Their presence is a coverage gap, never a clean-workspace assumption.
    """

    def _file(self, root, path, relative, limit):
        try:
            parents = _chain(root, path)
            before = path.lstat()
            if _link(before):
                return FileObservation(relative, "BLOCKED", "UNKNOWN")
            if not stat.S_ISREG(before.st_mode):
                return FileObservation(relative, "BLOCKED", "SPECIAL")
            if before.st_size > limit:
                return FileObservation(relative, "BLOCKED", "REGULAR", before.st_size)
            with _open_regular(root, path) as stream:
                opened = os.fstat(stream.fileno())
                if _link(opened):
                    return FileObservation(relative, "BLOCKED", "UNKNOWN")
                if not stat.S_ISREG(opened.st_mode) or _metadata(before) != _metadata(opened):
                    return FileObservation(relative, "RACE", "REGULAR")
                digest = hashlib.sha256()
                remaining = limit + 1
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
                after = os.fstat(stream.fileno())
                if remaining == 0 or _metadata(opened) != _metadata(after) or _metadata(path.lstat()) != _metadata(after) or parents != _chain(root, path):
                    return FileObservation(relative, "RACE", "REGULAR")
            return FileObservation(relative, "PRESENT", "REGULAR", after.st_size, digest.hexdigest(), _metadata(after))
        except FileNotFoundError:
            return FileObservation(relative, "RACE", "UNKNOWN")
        except VerificationError:
            return FileObservation(relative, "BLOCKED", "UNKNOWN")
        except (OSError, AttributeError):
            return FileObservation(relative, "UNAVAILABLE", "UNKNOWN")

    def observe(self, configuration, binding, phase, observed_at):
        entries = {}
        issues = []
        root = Path(configuration.repository_root)
        allowed = set(configuration.allowed_paths)
        ancestors = {p.as_posix() for name in allowed for p in Path(name).parents if p != Path(".")}
        count = 0
        pending = []
        directories = []

        def scan(directory):
            nonlocal count
            _chain(root, directory / "placeholder")
            before = directory.lstat()
            directories.append((directory, _metadata(before)))
            children = []
            with _directory_entries(root, directory) as iterator:
                for item in iterator:
                    count += 1
                    if count > configuration.max_files:
                        raise VerificationError("OBSERVATION_LIMIT")
                    relative = (directory / item.name).relative_to(root).as_posix()
                    _paths((relative,))
                    children.append(relative)
            _paths(tuple(children))
            for relative in sorted(children):
                path = root / relative
                info = path.lstat()
                if _link(info):
                    entries[relative] = FileObservation(relative, "BLOCKED", "UNKNOWN")
                elif stat.S_ISDIR(info.st_mode) and relative in ancestors:
                    entries[relative] = FileObservation(relative, "PRESENT", "DIRECTORY")
                    scan(path)
                elif relative in allowed:
                    pending.append(relative)
                    entries[relative] = FileObservation(relative, "UNAVAILABLE", "UNKNOWN")
                else:
                    kind = "DIRECTORY" if stat.S_ISDIR(info.st_mode) else "REGULAR" if stat.S_ISREG(info.st_mode) else "SPECIAL"
                    state = "BLOCKED" if kind == "SPECIAL" else "UNAVAILABLE"
                    entries[relative] = FileObservation(relative, state, kind, info.st_size, metadata=_metadata(info))
            if _metadata(before) != _metadata(directory.lstat()):
                issues.append("RACE")

        try:
            canonical_path(configuration.repository_root, directory=True)
            scan(root)
            for relative in sorted(allowed - entries.keys()):
                # A blocked ancestor must not be re-opened to seek a missing file.
                entries[relative] = FileObservation(relative, "ABSENT", "UNKNOWN")
            _paths(tuple(entries))
            if len(entries) > configuration.max_files:
                raise VerificationError("OBSERVATION_LIMIT")
            for relative in pending:
                entries[relative] = self._file(root, root / relative, relative, configuration.max_file_bytes)
            for directory, metadata in directories:
                if _metadata(directory.lstat()) != metadata:
                    issues.append("RACE")
            for entry in tuple(entries.values()):
                if entry.state == "PRESENT" and entry.file_type == "REGULAR":
                    if _metadata((root / entry.path).lstat()) != entry.metadata:
                        entries[entry.path] = FileObservation(entry.path, "RACE", "REGULAR")
        except VerificationError as error:
            issues.append("LIMIT" if str(error) == "OBSERVATION_LIMIT" else "UNTRUSTED")
        except FileNotFoundError:
            issues.append("RACE" if root.exists() else "UNTRUSTED")
        except OSError:
            issues.append("UNAVAILABLE")
        snapshot = WorkspaceSnapshot(binding, phase, observed_at, tuple(entries.values()), tuple(issues))
        if len(snapshot.canonical_json().encode()) > configuration.max_snapshot_bytes:
            return WorkspaceSnapshot(binding, phase, observed_at, (), ("LIMIT",))
        return snapshot


def compare_snapshots(pre, post, configuration):
    left = {e.path: e for e in pre.entries}
    right = {e.path: e for e in post.entries}
    changes = {"created": [], "modified": [], "deleted": [], "unchanged": [], "unsupported": []}
    for path in sorted(left.keys() | right.keys()):
        old, new = left.get(path), right.get(path)
        if any(e and e.state in ("BLOCKED", "RACE", "UNAVAILABLE") for e in (old, new)):
            changes["unsupported"].append(path)
        present_old = old is not None and old.state != "ABSENT"
        present_new = new is not None and new.state != "ABSENT"
        if not present_old and present_new:
            changes["created"].append(path)
        elif present_old and not present_new:
            changes["deleted"].append(path)
        elif old != new:
            changes["modified"].append(path)
        else:
            changes["unchanged"].append(path)
    expected = {c.path for c in configuration.expected_changes}
    ancestors = {p.as_posix() for c in configuration.expected_changes for p in Path(c.path).parents if p != Path(".")}
    touched = changes["created"] + changes["modified"] + changes["deleted"]
    unexpected = tuple(p for p in touched if p not in expected and p not in ancestors)
    return ChangeObservation(**{k: tuple(v) for k, v in changes.items()}, unexpected=unexpected)


@dataclass(frozen=True)
class IndependentVerifier:
    configuration: TrustedVerificationConfiguration
    observer: WorkspaceObserver
    runner: ProcessRunner
    clock: Clock
    _captured: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def _binding(self, packet, policy, decision):
        config = self.configuration
        try:
            config.__post_init__()
            packet = TaskPacket.model_validate(packet)
            policy = WorkspacePolicy.model_validate(policy)
            decision.validate_binding(packet, policy)
            if any((v.project_id, v.repository_root) != (config.project_id, config.repository_root) for v in (packet, policy)) or packet.task_id != config.task_id:
                raise ValueError()
        except (ValueError, OSError):
            raise VerificationError("BINDING_INVALID") from None
        return Binding(config.project_id, config.task_id, config.execution_id, config.repository_root,
                       packet.fingerprint(), policy.fingerprint(), decision.fingerprint(), config.fingerprint())

    def capture_pre(self, packet, policy, decision):
        binding = self._binding(packet, policy, decision)
        snapshot = self._observe(binding, "PRE")
        self._captured[binding.execution_id] = (snapshot, snapshot.fingerprint())
        return snapshot

    def _observe(self, binding, phase):
        now = self.clock.now()
        _time(now)
        try:
            snapshot = self.observer.observe(self.configuration, binding, phase, now)
            if type(snapshot) is not WorkspaceSnapshot or snapshot.binding != binding or snapshot.phase != phase or snapshot.observed_at != now:
                raise ValueError()
            snapshot.__post_init__()
            if len(snapshot.entries) > self.configuration.max_files or len(snapshot.canonical_json().encode()) > self.configuration.max_snapshot_bytes:
                raise ValueError()
            if not snapshot.issues and not set(self.configuration.allowed_paths) <= {e.path for e in snapshot.entries}:
                raise ValueError()
            return snapshot
        except Exception:
            return WorkspaceSnapshot(binding, phase, now, (), ("UNTRUSTED",))

    def _test(self, command):
        started = self.clock.now()
        try:
            outcome = ProcessOutcome.model_validate(self.runner.run(command.invocation))
            if outcome.started_at < started:
                raise ValueError()
            limit = self.configuration.max_output_bytes
            stdout, stderr = outcome.stdout.encode("utf-8"), outcome.stderr.encode("utf-8")
            out_cut = outcome.stdout_truncated or len(stdout) > min(limit, command.invocation.stdout_limit_bytes)
            err_cut = outcome.stderr_truncated or len(stderr) > min(limit, command.invocation.stderr_limit_bytes)
            if outcome.state != "EXITED":
                verdict, reason = VerificationVerdict.BLOCKED, "PROCESS_INCOMPLETE"
            elif outcome.exit_code != 0:
                verdict, reason = VerificationVerdict.FAILED, "NONZERO_EXIT"
            elif out_cut or err_cut:
                verdict, reason = VerificationVerdict.INCONCLUSIVE, "INCOMPLETE_OUTPUT"
            else:
                verdict, reason = VerificationVerdict.VERIFIED, "EXIT_ZERO_UNVERIFIED_TASK"
            return TestEvidence(command.command_id, command.fingerprint(), outcome.state, outcome.exit_code,
                                hashlib.sha256(stdout[:min(limit, command.invocation.stdout_limit_bytes)]).hexdigest(),
                                hashlib.sha256(stderr[:min(limit, command.invocation.stderr_limit_bytes)]).hexdigest(),
                                out_cut, err_cut, outcome.started_at, outcome.finished_at, verdict, reason)
        except Exception:
            finished = self.clock.now()
            return TestEvidence(command.command_id, command.fingerprint(), "RUNNER_ERROR", None, None, None,
                                False, False, started, max(started, finished), VerificationVerdict.BLOCKED, "RUNNER_FAILURE")

    def verify(self, packet, policy, decision, execution, pre, *, commands=None):
        binding = self._binding(packet, policy, decision)
        post = WorkspaceSnapshot(binding, "POST", self.clock.now(), (), ("UNTRUSTED",))
        reasons = []
        verdicts = []
        tests = ()
        changes = ChangeObservation()

        def add(verdict, reason):
            verdicts.append(verdict)
            reasons.append(reason)

        try:
            execution.validate_binding(packet, decision, policy)
            if (execution.execution_id != binding.execution_id or type(pre) is not WorkspaceSnapshot
                    or pre.binding != binding or pre.phase != "PRE" or pre.observed_at > execution.started_at
                    or self._captured.get(binding.execution_id, (None, None))[0] is not pre
                    or self._captured[binding.execution_id][1] != pre.fingerprint()):
                raise ValueError()
            pre.__post_init__()
        except (ValueError, AttributeError):
            raise VerificationError("BINDING_INVALID") from None
        requested = self.configuration.commands if commands is None else commands
        if type(requested) is not tuple or requested != self.configuration.commands:
            add(VerificationVerdict.BLOCKED, "COMMAND_NOT_APPROVED")
        else:
            post = self._observe(binding, "POST")
            if post.observed_at < execution.finished_at:
                add(VerificationVerdict.BLOCKED, "BINDING_INVALID")
            changes = compare_snapshots(pre, post, self.configuration)
            states = [e.state for s in (pre, post) for e in s.entries]
            issues = pre.issues + post.issues
            if "BLOCKED" in states or any(i in ("UNTRUSTED", "LIMIT") for i in issues):
                add(VerificationVerdict.BLOCKED, "OBSERVATION_BLOCKED")
            if any(s in ("RACE", "UNAVAILABLE") for s in states) or any(i in ("RACE", "UNAVAILABLE") for i in issues):
                add(VerificationVerdict.INCONCLUSIVE, "OBSERVATION_UNCERTAIN")
            if changes.unexpected:
                add(VerificationVerdict.FAILED, "UNEXPECTED_CHANGE")
            if changes.deleted and not self.configuration.allow_deletions:
                add(VerificationVerdict.FAILED, "DELETION_PROHIBITED")
            actual = {"CREATED": changes.created, "MODIFIED": changes.modified, "DELETED": changes.deleted}
            old_entries = {e.path: e for e in pre.entries}
            new_entries = {e.path: e for e in post.entries}
            for requirement in self.configuration.expected_changes:
                matches = requirement.path in actual[requirement.kind]
                if matches and requirement.kind == "MODIFIED" and requirement.path not in changes.unsupported:
                    matches = old_entries[requirement.path].content_digest != new_entries[requirement.path].content_digest
                if not matches and requirement.path not in changes.unsupported and not issues:
                    add(VerificationVerdict.FAILED, "EXPECTED_CHANGE_MISSING")
            if not verdicts:
                tests = tuple(self._test(command) for command in requested)
                for test in tests:
                    if test.verdict != VerificationVerdict.VERIFIED:
                        add(test.verdict, "TEST_NOT_PASSED")
                final = self._observe(binding, "POST")
                if final.entries != post.entries or final.issues != post.issues:
                    add(VerificationVerdict.BLOCKED, "TEST_MUTATED_WORKSPACE")
                post = final
                changes = compare_snapshots(pre, post, self.configuration)
        verdict = next((v for v in (VerificationVerdict.BLOCKED, VerificationVerdict.FAILED,
                                    VerificationVerdict.INCONCLUSIVE) if v in verdicts), VerificationVerdict.VERIFIED)
        created = self.clock.now()
        _time(created)
        if created < post.observed_at or any(t.finished_at > created for t in tests):
            raise VerificationError("BINDING_INVALID")
        evidence = VerificationEvidence(binding, execution.fingerprint(), pre.fingerprint(), post.fingerprint(),
                                        changes, tests, verdict, tuple(reasons or ["OBSERVED_REQUIREMENTS_MET"]), created)
        if len(evidence.canonical_json().encode()) > self.configuration.max_evidence_bytes:
            evidence = replace(evidence, changes=ChangeObservation(), tests=(), verdict=VerificationVerdict.BLOCKED,
                               reason_codes=("EVIDENCE_LIMIT",))
        evidence.fingerprint()  # validate the entire canonical payload before returning
        return evidence
