"""Isolated G3 checks: temporary workspaces, fake clocks/runners by default."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, OperationRule, RequestedOperation, TaskPacket, WorkspacePolicy,
)
from zero_core.engineering_execution import ProcessInvocation, ProcessOutcome
from zero_core.engineering_verification import (
    ChangeObservation, ExpectedChange, FileObservation, IndependentVerifier, LocalWorkspaceObserver,
    TrustedVerificationConfiguration, VerificationCommand, VerificationError, VerificationVerdict,
    WorkspaceSnapshot,
)


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)
PYTHON = Path(sys._base_executable).resolve().as_posix()
V = VerificationVerdict


class FakeClock:
    def __init__(self):
        self.value = NOW

    def now(self):
        return self.value


class FakeRunner:
    def __init__(self, clock, outcomes=()):
        self.clock = clock
        self.outcomes = list(outcomes)
        self.calls = []

    def run(self, invocation):
        self.calls.append(invocation)
        changes = self.outcomes.pop(0) if self.outcomes else {}
        if isinstance(changes, Exception):
            raise changes
        return ProcessOutcome("EXITED", self.clock.now(), self.clock.now(), 0,
                              stdout="149 tests passed, changed secret-file.py").model_copy(update=changes)


def command(root, name="check", **changes):
    invocation = ProcessInvocation((PYTHON, "-B", "-I", "-c", "pass"), "", root.as_posix(), {"LANG": "C"})
    return VerificationCommand(name, replace(invocation, **changes))


class Scenario:
    def __init__(self, root, *, kind="CREATED", allowed=("a.txt",), expected=None, commands=None, **config):
        self.root = root
        self.root.mkdir()
        self.clock = FakeClock()
        self.runner = FakeRunner(self.clock)
        self.config = TrustedVerificationConfiguration(
            "project", "task", "attempt", root.as_posix(), allowed,
            expected if expected is not None else (ExpectedChange("a.txt", kind),),
            commands if commands is not None else (command(root),), **config)
        op = RequestedOperation(action="CREATE_FILE", target="a.txt")
        self.packet = TaskPacket(packet_id="packet", project_id="project", task_id="task", milestone_id="milestone",
                                 repository_root=root.as_posix(), policy_id="policy", policy_version=1,
                                 context_fingerprint="a" * 64, operations=(op,), created_at=NOW)
        self.policy = WorkspacePolicy(policy_id="policy", policy_version=1, project_id="project",
                                      repository_root=root.as_posix(), rules=(OperationRule(operation=op, outcome="LOW_RISK"),))
        self.decision = self.policy.evaluate(self.packet, decision_id="decision", evaluated_at=NOW)
        self.verifier = IndependentVerifier(self.config, LocalWorkspaceObserver(), self.runner, self.clock)

    def pre(self):
        self.snapshot = self.verifier.capture_pre(self.packet, self.policy, self.decision)
        self.clock.value = NOW + timedelta(seconds=2)
        return self.snapshot

    def execution(self, **changes):
        return EngineeringExecutionResult(
            execution_id="attempt", executor_id="untrusted-worker", project_id="project", task_id="task",
            packet_fingerprint=self.packet.fingerprint(), permission_decision_id=self.decision.decision_id,
            status="SUCCESS", started_at=NOW + timedelta(seconds=1), finished_at=NOW + timedelta(seconds=2),
            summary="All files changed and 149 tests passed. Verified!",
        ).model_copy(update=changes)

    def verify(self, *, execution=None, **kwargs):
        return self.verifier.verify(self.packet, self.policy, self.decision,
                                    execution or self.execution(), self.snapshot, **kwargs)


@pytest.fixture
def scenario(tmp_path):
    return Scenario(tmp_path / "repo")


@pytest.mark.parametrize("kind", ["CREATED", "MODIFIED", "DELETED"])
def test_expected_observed_changes(tmp_path, kind):
    s = Scenario(tmp_path / "repo", kind=kind, allow_deletions=True)
    file = s.root / "a.txt"
    if kind != "CREATED":
        file.write_text("before", encoding="utf-8")
    s.pre()
    if kind == "DELETED":
        file.unlink()
    else:
        file.write_text("after", encoding="utf-8")
    evidence = s.verify()
    assert evidence.verdict == V.VERIFIED
    assert getattr(evidence.changes, kind.lower()) == ("a.txt",)
    assert len(s.runner.calls) == 1


def test_unapproved_deletion(tmp_path):
    s = Scenario(tmp_path / "repo", kind="DELETED")
    (s.root / "a.txt").write_text("before", encoding="utf-8")
    s.pre()
    (s.root / "a.txt").unlink()
    result = s.verify()
    assert result.verdict == V.FAILED and "DELETION_PROHIBITED" in result.reason_codes


@pytest.mark.parametrize("kind", ["CREATED", "MODIFIED", "DELETED"])
def test_unexpected_changes_without_content_reads(tmp_path, kind, monkeypatch):
    s = Scenario(tmp_path / "repo")
    outside = s.root / "unapproved.txt"
    if kind != "CREATED":
        outside.write_text("opaque baseline", encoding="utf-8")
    import zero_core.engineering_verification as module
    original = module._open_regular

    def guarded(root, path):
        assert path != outside, "unapproved content must not be opened"
        return original(root, path)

    monkeypatch.setattr(module, "_open_regular", guarded)
    s.pre()
    (s.root / "a.txt").write_text("expected", encoding="utf-8")
    if kind == "DELETED":
        outside.unlink()
    else:
        outside.write_text("different metadata and size", encoding="utf-8")
    result = s.verify()
    assert result.verdict == V.FAILED and result.changes.unexpected == ("unapproved.txt",)


@pytest.mark.parametrize("claim", [
    {}, {"reported_files_created": ("a.txt",)}, {"reported_files_modified": ("a.txt",)},
    {"tests_executed": 149, "tests_passed": 149},
])
def test_executor_claims_do_not_create_observations(scenario, claim):
    s = scenario
    s.pre()
    result = s.verify(execution=s.execution(**claim))
    assert result.verdict == V.FAILED
    assert result.changes.created == () and result.changes.modified == ()
    assert "EXPECTED_CHANGE_MISSING" in result.reason_codes and s.runner.calls == []


def test_executor_test_prose_does_not_override_failed_runner(scenario):
    s = scenario
    s.pre()
    (s.root / "a.txt").write_text("done", encoding="utf-8")
    s.runner.outcomes = [{"exit_code": 9, "stdout": "149 tests passed"}]
    result = s.verify(execution=s.execution(tests_executed=149, tests_passed=149))
    assert result.verdict == V.FAILED
    assert result.tests[0].exit_code == 9
    assert "149 tests" not in result.canonical_json()


def test_hashes_no_content_and_stable_fingerprint(tmp_path):
    s = Scenario(tmp_path / "repo", kind="MODIFIED")
    (s.root / "a.txt").write_text("raw-content-never-in-evidence-before", encoding="utf-8")
    pre = s.pre()
    (s.root / "a.txt").write_text("raw-content-never-in-evidence-after", encoding="utf-8")
    post = s.verifier._observe(pre.binding, "POST")
    assert pre.entries[0].content_digest != post.entries[0].content_digest
    result = s.verify()
    assert result.fingerprint() == s.verify().fingerprint()
    assert "raw-content-never" not in result.canonical_json() + pre.canonical_json() + post.canonical_json()
    assert result.fingerprint_kind == "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"
    assert "stdin" not in result.canonical_json() and "environment" not in result.canonical_json()
    for change in ({"verdict": V.FAILED}, {"pre_digest": "f" * 64}, {"post_digest": "f" * 64},
                   {"execution_digest": "f" * 64}, {"changes": ChangeObservation()}, {"tests": ()},
                   {"verdict": V.FAILED, "reason_codes": ("EXPECTED_CHANGE_MISSING",)}, {"created_at": NOW + timedelta(seconds=3)},
                   {"binding": replace(result.binding, task_id="other")}):
        assert replace(result, **change).fingerprint() != result.fingerprint()


@pytest.mark.parametrize("field,value", [("project_id", "other"), ("task_id", "other"), ("execution_id", "other"),
                                        ("packet_fingerprint", "f" * 64), ("permission_decision_id", "other")])
def test_execution_binding_blocks(scenario, field, value):
    s = scenario
    s.pre()
    with pytest.raises(VerificationError, match="BINDING_INVALID"):
        s.verify(execution=s.execution(**{field: value}))
    assert not s.runner.calls


@pytest.mark.parametrize("owner", ["packet", "policy", "configuration"])
def test_project_mismatch_blocks(scenario, owner):
    s = scenario
    if owner == "configuration":
        verifier = replace(s.verifier, configuration=replace(s.config, project_id="other"))
    else:
        record = getattr(s, owner)
        setattr(s, owner, record.model_copy(update={"project_id": "other"}))
        verifier = s.verifier
    with pytest.raises(VerificationError, match="BINDING_INVALID"):
        verifier.capture_pre(s.packet, s.policy, s.decision)
    assert not s.runner.calls


def test_matching_task_policy_root_cannot_override_trust(scenario, tmp_path):
    s = scenario
    other = tmp_path / "other"
    other.mkdir()
    s.packet = s.packet.model_copy(update={"repository_root": other.as_posix()})
    s.policy = s.policy.model_copy(update={"repository_root": other.as_posix()})
    s.decision = s.policy.evaluate(s.packet, decision_id="new")
    with pytest.raises(VerificationError):
        s.pre()
    assert not s.runner.calls


@pytest.mark.parametrize("path", ["/absolute", "C:/absolute", "../x", "a/../b", "a//b", "a\\b", "\\\\host\\x",
                                  "a:stream", "NUL", "a\x00b", "", "a/./b", "A/", "COM1.txt"])
def test_untrusted_paths_block(tmp_path, path):
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(ValueError):
        TrustedVerificationConfiguration("project", "task", "attempt", root.as_posix(), (path,), ())


@pytest.mark.parametrize("parent", [False, True])
def test_reparse_target_and_parent_never_opened(tmp_path, monkeypatch, parent):
    s = Scenario(tmp_path / "repo", allowed=("sub/a.txt",), expected=(ExpectedChange("sub/a.txt", "MODIFIED"),))
    (s.root / "sub").mkdir()
    (s.root / "sub/a.txt").write_text("before", encoding="utf-8")
    target = s.root / ("sub" if parent else "sub/a.txt")
    original = Path.lstat

    class Info:
        st_file_attributes = 0x400
        st_mode = stat.S_IFDIR if parent else stat.S_IFREG

    def lstat(path, *args, **kwargs):
        return Info() if path == target else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    s.pre()
    assert s.verify().verdict == V.BLOCKED
    assert not s.runner.calls


@pytest.mark.parametrize("paths", [("a.txt", "a.txt"), ("a.txt", "A.TXT")])
def test_duplicate_casefold_paths_rejected(tmp_path, paths):
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(VerificationError):
        TrustedVerificationConfiguration("project", "task", "attempt", root.as_posix(), paths, ())


def test_oversized_and_excessive_files_block(tmp_path):
    s = Scenario(tmp_path / "repo", max_file_bytes=2, max_files=2)
    s.pre()
    (s.root / "a.txt").write_text("too large", encoding="utf-8")
    assert s.verify().verdict == V.BLOCKED
    (s.root / "b").touch()
    (s.root / "c").touch()
    assert s.verify().verdict == V.BLOCKED


def test_special_files_not_opened(scenario, monkeypatch):
    s = scenario
    (s.root / "a.txt").touch()
    original = Path.lstat

    class Special:
        st_mode = stat.S_IFIFO
        st_file_attributes = 0
        st_size = 0

    def lstat(path, *args, **kwargs):
        return Special() if path == s.root / "a.txt" else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    import zero_core.engineering_verification as module
    def forbidden(*args):
        raise AssertionError("special-file content opened")
    monkeypatch.setattr(module, "_open_regular", forbidden)
    s.pre()
    assert s.verify().verdict == V.BLOCKED


def test_replacement_race_cannot_verify(tmp_path, monkeypatch):
    s = Scenario(tmp_path / "repo", kind="MODIFIED")
    (s.root / "a.txt").write_text("before", encoding="utf-8")
    s.pre()
    import zero_core.engineering_verification as module
    original = module._open_regular
    def replaced(root, path):
        replacement = root / "replacement.tmp"
        replacement.write_text("replacement bytes", encoding="utf-8")
        replacement.replace(path)
        return original(root, path)
    monkeypatch.setattr(module, "_open_regular", replaced)
    assert s.verify().verdict == V.INCONCLUSIVE


@pytest.mark.parametrize("field", ["argv", "cwd", "environment", "stdin", "timeout_seconds", "stdout_limit_bytes", "stderr_limit_bytes"])
def test_only_exact_approved_command_runs(scenario, tmp_path, field):
    s = scenario
    s.pre()
    (s.root / "a.txt").write_text("done", encoding="utf-8")
    original = s.config.commands[0]
    changes = {"argv": original.invocation.argv + ("extra",), "cwd": tmp_path.as_posix(),
               "environment": {"LANG": "C.UTF-8"}, "stdin": "injected", "timeout_seconds": 2,
               "stdout_limit_bytes": 100, "stderr_limit_bytes": 100}
    altered = replace(original, invocation=replace(original.invocation, **{field: changes[field]}))
    result = s.verify(commands=(altered,))
    assert result.verdict == V.BLOCKED and not s.runner.calls


def test_unapproved_or_missing_command_has_no_runner_calls(scenario):
    s = scenario
    s.pre()
    for commands in ((), (replace(s.config.commands[0], command_id="unknown"),)):
        assert s.verify(commands=commands).verdict == V.BLOCKED
    assert not s.runner.calls


@pytest.mark.parametrize("outcome,verdict", [
    ({"exit_code": 1}, V.FAILED),
    ({"exit_code": 1, "stdout_truncated": True}, V.FAILED),
    ({"state": "TIMEOUT", "exit_code": None}, V.BLOCKED),
    ({"state": "CANCELLED", "exit_code": None}, V.BLOCKED),
    ({"state": "MISSING_EXECUTABLE", "exit_code": None}, V.BLOCKED),
    ({"stdout_truncated": True}, V.INCONCLUSIVE),
    ({"stderr_truncated": True}, V.INCONCLUSIVE),
    ({"stdout": "x" * 5000}, V.INCONCLUSIVE),
    (RuntimeError("secret prompt password" * 2000), V.BLOCKED),
])
def test_test_failure_modes(scenario, outcome, verdict):
    s = scenario
    s.pre()
    (s.root / "a.txt").write_text("done", encoding="utf-8")
    s.runner.outcomes = [outcome]
    result = s.verify()
    assert result.verdict == verdict and len(result.tests) == 1
    assert "secret prompt" not in result.canonical_json()
    assert len(result.tests[0].reason) < 100


def test_all_required_commands_and_duplicate_ids(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    a, b = command(root, "a"), command(root, "b")
    with pytest.raises(VerificationError):
        TrustedVerificationConfiguration("project", "task", "attempt", root.as_posix(), (), (), (a, a))
    root.rmdir()
    s = Scenario(root, commands=(a, b))
    s.pre()
    (root / "a.txt").write_text("done", encoding="utf-8")
    s.runner.outcomes = [{}, {"exit_code": 1}]
    result = s.verify()
    assert len(s.runner.calls) == 2 and result.verdict == V.FAILED


def test_ordering_immutability_and_snapshot_provenance(scenario):
    s = scenario
    pre = s.pre()
    entries = (FileObservation("z.txt", "ABSENT", "UNKNOWN"), FileObservation("b.txt", "ABSENT", "UNKNOWN"))
    ordered = replace(pre, entries=entries)
    assert [e.path for e in ordered.entries] == ["b.txt", "z.txt"]
    with pytest.raises(VerificationError):
        replace(pre, entries=(entries[0], entries[0]))
    for obj, field, value in ((pre, "phase", "POST"), (s.config, "project_id", "other"),
                              (entries[0], "size", 50), (s.config.commands[0], "command_id", "other")):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)
    with pytest.raises(VerificationError):
        s.verifier.verify(s.packet, s.policy, s.decision, s.execution(), replace(pre))


def test_opaque_branch_not_recursed_and_not_assumed_unchanged(scenario, monkeypatch):
    s = scenario
    opaque = s.root / "opaque"
    opaque.mkdir()
    (opaque / "unreadable.txt").write_text("must not read", encoding="utf-8")
    original = os.scandir
    def guarded(path):
        assert Path(path) != opaque, "unapproved directory recursion"
        return original(path)
    monkeypatch.setattr(os, "scandir", guarded)
    s.pre()
    (s.root / "a.txt").write_text("done", encoding="utf-8")
    assert s.verify().verdict == V.INCONCLUSIVE


def test_test_side_effects_cannot_verify(scenario):
    s = scenario
    s.pre()
    (s.root / "a.txt").write_text("done", encoding="utf-8")
    class MutatingRunner:
        def run(self, invocation):
            (s.root / "a.txt").write_text("test changed workspace", encoding="utf-8")
            return s.runner.run(invocation)
    object.__setattr__(s.verifier, "runner", MutatingRunner())
    assert s.verify().verdict == V.BLOCKED


@pytest.mark.skipif(os.name != "nt", reason="G2B runner supports Windows only")
def test_harmless_real_fixture_through_g2_runner(tmp_path):
    from zero_core.process_runner import LocalProcessRunner
    s = Scenario(tmp_path / "repo", commands=())
    path = Path(__file__).parent / "fixtures/verification_fixture.py"
    content = b"independently checked"
    invocation = ProcessInvocation((PYTHON, "-B", "-I", str(path.resolve()), "a.txt", hashlib.sha256(content).hexdigest()),
                                   "", s.root.as_posix(), {"LANG": "C"})
    s.config = replace(s.config, commands=(VerificationCommand("fixture", invocation),))
    class RealClock:
        def now(self):
            return datetime.now(timezone.utc)
    s.clock = RealClock()
    s.verifier = IndependentVerifier(s.config, LocalWorkspaceObserver(), LocalProcessRunner(), s.clock)
    pre = s.verifier.capture_pre(s.packet, s.policy, s.decision)
    started = s.clock.now()
    (s.root / "a.txt").write_bytes(content)
    execution = s.execution(started_at=started, finished_at=s.clock.now())
    result = s.verifier.verify(s.packet, s.policy, s.decision, execution, pre)
    assert result.verdict == V.VERIFIED and result.tests[0].exit_code == 0


def test_import_inert(tmp_path):
    script = r'''
import sys, os, dataclasses, datetime, enum, hashlib, json, pathlib, re, stat, typing
sys.path.insert(0, sys.argv[1])
import zero_core.engineering_execution
def forbidden(*args, **kwargs):
    raise AssertionError("environment read")
os.getenv = forbidden
type(os.environ).__getitem__ = forbidden
def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise AssertionError("write")
    if event in {"subprocess.Popen", "os.system", "os.mkdir", "os.remove", "os.rename", "ctypes.dlopen"} or event.startswith("socket."):
        raise AssertionError("resource during import")
sys.addaudithook(audit)
import zero_core.engineering_verification
assert "zero_core.process_runner" not in sys.modules
assert "zero_core.config" not in sys.modules
assert "zero_core.engineering" not in sys.modules
print("INERT")
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(Path(__file__).resolve().parents[2])],
                            capture_output=True, cwd=tmp_path, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "INERT" and not list(tmp_path.iterdir())


def test_path_and_handle_metadata_agree(tmp_path):
    from zero_core.engineering_verification import _metadata, _open_regular
    path = tmp_path / "observed.txt"
    path.write_bytes(b"fixture")
    before = _metadata(path.lstat())
    with _open_regular(tmp_path, path) as stream:
        opened = _metadata(os.fstat(stream.fileno()))
        stream.read()
        after = _metadata(os.fstat(stream.fileno()))
        final = _metadata(path.lstat())
    assert before == opened == after == final


def test_same_content_rewrite_is_not_required_modification(tmp_path):
    s = Scenario(tmp_path / "repo", kind="MODIFIED")
    path = s.root / "a.txt"
    path.write_text("same", encoding="utf-8")
    s.pre()
    path.write_text("same", encoding="utf-8")
    assert s.verify().verdict == V.FAILED


def test_inventory_limit_precedes_hashing(scenario, monkeypatch):
    s = scenario
    object.__setattr__(s.verifier, "configuration", replace(s.config, max_files=1))
    (s.root / "a.txt").touch()
    (s.root / "z.txt").touch()
    import zero_core.engineering_verification as module
    def forbidden(*args):
        raise AssertionError("hashing before count check")
    monkeypatch.setattr(module, "_open_regular", forbidden)
    s.pre()
    assert s.verify().verdict == V.BLOCKED


def test_missing_root_blocks(scenario):
    s = scenario
    s.root.rmdir()
    with pytest.raises(VerificationError):
        s.pre()
    assert not s.runner.calls


def test_snapshot_and_evidence_size_limits(tmp_path):
    s = Scenario(tmp_path / "repo", max_snapshot_bytes=10)
    s.pre()
    assert s.verify().verdict == V.BLOCKED
    root = tmp_path / "many"
    root.mkdir()
    commands = tuple(command(root, "check-" + str(i)) for i in range(12))
    root.rmdir()
    s = Scenario(root, commands=commands, max_evidence_bytes=4096)
    s.pre()
    (root / "a.txt").write_text("done", encoding="utf-8")
    result = s.verify()
    assert result.verdict == V.BLOCKED and result.reason_codes == ("EVIDENCE_LIMIT",)
    assert len(result.canonical_json().encode()) <= 4096


def test_unknown_observer_result_blocks(scenario):
    s = scenario
    class InvalidObserver:
        def observe(self, *args):
            return "all files verified"
    object.__setattr__(s.verifier, "observer", InvalidObserver())
    s.pre()
    assert s.verify().verdict == V.BLOCKED and not s.runner.calls
