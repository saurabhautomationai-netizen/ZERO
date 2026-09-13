"""Isolated G2A tests. Every executor runner is a fake."""

from dataclasses import fields, FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from zero_core.engineering_contracts import OperationRule, RequestedOperation, TaskPacket, WorkspacePolicy
from zero_core.engineering_execution import (
    ProcessInvocation, ProcessOutcome, TrustedAdapterConfiguration, execute_attempt,
)
from zero_core.external_executor_adapters import CodexAdapter, GooseAdapter


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


class FakeRunner:
    def __init__(self, **changes):
        self.calls = []
        self.outcome = ProcessOutcome(state="EXITED", exit_code=0, stdout='{"fixture_v1":"success"}',
                                      started_at=NOW, finished_at=NOW).model_copy(update=changes)

    def run(self, invocation):
        self.calls.append(invocation)
        return self.outcome


class FixtureAdapter:
    """Test-only versioned protocol, explicitly NOT a Codex/Goose schema."""
    executor_id = "fixture"

    def __init__(self, configuration):
        self.configuration = configuration

    def plan(self, packet):
        c = self.configuration
        return ProcessInvocation((c.executable, "fixture"), "sanitized fixed instruction\n",
                                 c.repository_root, c.environment)

    def parse(self, output):
        if output != '{"fixture_v1":"success"}':
            raise ValueError("unknown fixture schema")
        return True


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    executable = tmp_path / "fixture.exe"
    executable.write_bytes(b"fake; never executed")
    executable.chmod(0o700)
    home = tmp_path / "isolated-home"
    home.mkdir()
    config = TrustedAdapterConfiguration("project", root.as_posix(), executable.as_posix(),
                                         {"CODEX_HOME": home.as_posix(), "LANG": "C"})
    op = RequestedOperation(action="READ_FILE", target="src/main.py")
    packet = TaskPacket(packet_id="packet", project_id="project", task_id="task", milestone_id="milestone",
                        repository_root=config.repository_root, policy_id="policy", policy_version=1,
                        context_fingerprint="a" * 64, operations=(op,))
    policy = WorkspacePolicy(policy_id="policy", policy_version=1, project_id="project",
                             repository_root=config.repository_root,
                             rules=(OperationRule(operation=op, outcome="LOW_RISK"),))
    return config, packet, policy


def attempt(setup, runner=None, adapter=None, decision=None):
    config, packet, policy = setup
    return execute_attempt(packet, policy, decision or policy.evaluate(packet, decision_id="decision"),
                           adapter or FixtureAdapter(config), runner or FakeRunner(), execution_id="attempt")


def effect_free(result):
    assert not result.reported_files_created
    assert not result.reported_files_modified
    assert not result.reported_files_deleted
    assert result.tests_executed == result.tests_passed == result.tests_failed == result.tests_skipped == 0


@pytest.mark.parametrize("outcome", ["DENIED", "HITL_REQUIRED"])
def test_permission_gate(setup, outcome):
    c, p, policy = setup
    policy = policy.model_copy(update={"rules": (OperationRule(operation=p.operations[0], outcome=outcome),)})
    runner = FakeRunner()
    result = attempt((c, p, policy), runner)
    assert result.status == "BLOCKED" and runner.calls == []
    effect_free(result)


@pytest.mark.parametrize("change", [
    {"packet_fingerprint": "b" * 64}, {"policy_fingerprint": "b" * 64},
    {"outcome": "DENIED"}, {"reason_codes": ("FABRICATED",)},
])
def test_tampered_decision(setup, change):
    _, p, policy = setup
    decision = policy.evaluate(p, decision_id="decision").model_copy(update=change)
    runner = FakeRunner()
    result = attempt(setup, runner, decision=decision)
    assert result.status == "BLOCKED" and not runner.calls
    effect_free(result)


def test_stale_packet_and_policy(setup):
    c, p, policy = setup
    decision = policy.evaluate(p, decision_id="decision")
    for packet, rules in [(p.model_copy(update={"context_fingerprint": "b" * 64}), policy),
                          (p, policy.model_copy(update={"policy_version": 2}))]:
        runner = FakeRunner()
        assert attempt((c, packet, rules), runner, decision=decision).status == "BLOCKED"
        assert not runner.calls


@pytest.mark.parametrize("field", ["project_id", "repository_root"])
def test_matching_packet_policy_cannot_override_trust(setup, tmp_path, field):
    c, p, policy = setup
    other = tmp_path / "other"
    other.mkdir()
    value = "other" if field == "project_id" else other.as_posix()
    runner = FakeRunner()
    result = attempt((c, p.model_copy(update={field: value}), policy.model_copy(update={field: value})), runner)
    assert result.status == "BLOCKED" and not runner.calls
    effect_free(result)


def test_missing_root_and_executable_rechecked(setup):
    c, _, _ = setup
    Path(c.executable).unlink()
    runner = FakeRunner()
    assert attempt(setup, runner).status == "BLOCKED" and not runner.calls
    with pytest.raises((ValueError, OSError)):
        TrustedAdapterConfiguration(c.project_id, c.repository_root, c.executable, {})
    Path(c.repository_root).rmdir()
    assert attempt(setup, runner).status == "BLOCKED" and not runner.calls


def test_paths_fail_closed(setup, monkeypatch):
    c, _, _ = setup
    for root in ("", "relative", c.repository_root + "/missing"):
        with pytest.raises((ValueError, OSError)):
            TrustedAdapterConfiguration("project", root, c.executable, {})
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        if path.as_posix() == c.repository_root:
            class Info:
                st_mode = 0o40755
                st_file_attributes = 0x400
            return Info()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", reparse)
    runner = FakeRunner()
    assert attempt(setup, runner).status == "BLOCKED" and not runner.calls


def test_symlink_and_unsupported_platform(setup, monkeypatch):
    import zero_core.engineering_execution as boundary
    c, _, _ = setup
    original = Path.lstat

    def symlink(path, *args, **kwargs):
        if path.as_posix() == c.repository_root:
            class Info:
                st_mode = 0o120777
            return Info()
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", symlink)
        runner = FakeRunner()
        assert attempt(setup, runner).status == "BLOCKED" and not runner.calls
    with monkeypatch.context() as patch:
        patch.setattr(boundary.os, "name", "unsupported")
        with pytest.raises(ValueError, match="unsupported platform"):
            boundary.canonical_path(c.repository_root, directory=True)


def test_configuration_copies_environment(setup):
    c, _, _ = setup
    supplied = {"LANG": "C"}
    config = TrustedAdapterConfiguration(c.project_id, c.repository_root, c.executable, supplied)
    supplied["LANG"] = "changed"
    assert config.environment["LANG"] == "C"
    with pytest.raises(FrozenInstanceError):
        config.project_id = "other"


def test_invalid_runner_record_and_planner_binding(setup):
    class InvalidRunner:
        def run(self, invocation):
            return {"state": "EXITED", "exit_code": 0}
    assert attempt(setup, InvalidRunner()).status == "FAILED"

    class WrongEnvironment(FixtureAdapter):
        def plan(self, packet):
            c = self.configuration
            return ProcessInvocation((c.executable,), "fixed", c.repository_root, {})
    runner = FakeRunner()
    assert attempt(setup, runner, WrongEnvironment(setup[0])).status == "BLOCKED"
    assert not runner.calls


def test_exact_codex_preview_and_environment(setup, monkeypatch):
    c, packet, _ = setup
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")
    monkeypatch.setenv("CUSTOM_PROVIDER_TOKEN", "ambient-secret")
    monkeypatch.setenv("CODEX_HOME", "ambient-provider-home")
    invocation = CodexAdapter(c).preview(packet)
    assert invocation.argv == (c.executable, "exec", "--ignore-user-config", "--strict-config",
                               "--ephemeral", "--json", "--color", "never", "--sandbox", "read-only",
                               "-c", 'model_provider="openai"', "-C", c.repository_root, "-")
    assert invocation.stdin == '{"files":["src/main.py"],"instruction":"Read only the listed repository files. Report observations."}\n'
    assert invocation.cwd == c.repository_root
    assert dict(invocation.environment) == {"CODEX_HOME": c.environment["CODEX_HOME"], "LANG": "C"}
    assert "ambient" not in repr(invocation)
    assert invocation.timeout_seconds == 60
    assert (invocation.stdout_limit_bytes, invocation.stderr_limit_bytes) == (65536, 4096)
    assert "shell" not in {f.name for f in fields(ProcessInvocation)}
    with pytest.raises(TypeError):
        invocation.environment["OPENAI_API_KEY"] = "secret"
    with pytest.raises(FrozenInstanceError):
        invocation.stdin = "other"


def test_no_packet_environment_approval_or_command_prompt(setup):
    c, packet, _ = setup
    for field in ("environment", "approved", "approval_token", "context"):
        with pytest.raises(ValueError):
            packet.model_copy(update={field: {"KEY": "secret"}})
    with pytest.raises(ValueError):
        TrustedAdapterConfiguration(c.project_id, c.repository_root, c.executable, {"OPENAI_API_KEY": "secret"})
    command = RequestedOperation(action="RUN_COMMAND", command_id="test", arguments=("secret",), working_directory=".")
    with pytest.raises(ValueError):
        CodexAdapter(c).preview(packet.model_copy(update={"operations": (command,)}))


@pytest.mark.parametrize("adapter_type", [CodexAdapter, GooseAdapter])
def test_unproven_cli_capabilities_block(setup, adapter_type):
    runner = FakeRunner()
    assert attempt(setup, runner, adapter_type(setup[0])).status == "BLOCKED"
    assert not runner.calls
    for output in ('{}', '{"type":"turn.completed"}', 'session-id', ''):
        with pytest.raises(ValueError):
            adapter_type(setup[0]).parse(output)


def test_codex_unknown_version_rejected(setup):
    with pytest.raises(ValueError):
        CodexAdapter(setup[0], cli_version="future").preview(setup[1])


@pytest.mark.parametrize("changes,expected", [
    ({"exit_code": 1, "stderr": "secret\x1b[31m"}, "FAILED"),
    ({"state": "MISSING_EXECUTABLE", "exit_code": None}, "BLOCKED"),
    ({"state": "TIMEOUT", "exit_code": None}, "TIMEOUT"),
    ({"state": "CANCELLED", "exit_code": None}, "CANCELLED"),
    ({"stdout": "{"}, "FAILED"),
    ({"stdout": '{"fixture_v2":"success"}'}, "FAILED"),
    ({"stdout": '{"fixture_v1":"success","verified":true}'}, "FAILED"),
    ({"stdout_truncated": True}, "FAILED"),
    ({"stderr_truncated": True}, "FAILED"),
    ({"stdout": "\u2603" * 30000}, "FAILED"),
    ({"stdout": "Created a.py and passed 999 tests. Verified!"}, "FAILED"),
])
def test_outcomes_fail_closed(setup, changes, expected):
    runner = FakeRunner(**changes)
    result = attempt(setup, runner)
    assert len(runner.calls) == 1 and result.status == expected
    assert "secret" not in result.summary and "\x1b" not in result.summary
    effect_free(result)


def test_success_is_only_unverified_attempt(setup):
    runner = FakeRunner()
    result = attempt(setup, runner)
    assert result.status == "SUCCESS" and "unverified" in result.summary
    assert len(runner.calls) == 1
    effect_free(result)
    for field in ("verified", "checkpoint_id", "milestone_completed", "session_id"):
        assert field not in type(result).model_fields


def test_runner_exception_is_redacted(setup):
    class BrokenRunner:
        def run(self, invocation):
            raise RuntimeError("password=secret" * 10000)
    result = attempt(setup, BrokenRunner())
    assert result.status == "FAILED" and "secret" not in result.summary


def test_import_inert(tmp_path):
    root = str(Path(__file__).resolve().parents[2])
    script = r'''
import sys, os, pathlib, dataclasses, types, typing, stat, json
sys.path.insert(0, sys.argv[1])
import zero_core.engineering_contracts
def forbidden(*args, **kwargs):
    raise AssertionError("environment read during import")
os.getenv = forbidden
type(os.environ).__getitem__ = forbidden
def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise AssertionError("write")
    if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.system", "subprocess.Popen"} or event.startswith("socket."):
        raise AssertionError(event)
sys.addaudithook(audit)
import zero_core.engineering_execution
import zero_core.external_executor_adapters
assert "zero_core.engineering" not in sys.modules
assert "zero_core.config" not in sys.modules
print("INERT")
'''
    completed = subprocess.run([sys.executable, "-B", "-c", script, root], cwd=tmp_path,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "INERT"
    assert list(tmp_path.iterdir()) == []
