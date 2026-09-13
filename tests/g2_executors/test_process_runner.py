"""G2B local fixture tests. No AI executors or operational ZERO imports."""

import ctypes
from ctypes import wintypes
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from zero_core.engineering_execution import ProcessInvocation
from zero_core.process_runner import LocalProcessRunner, RunnerError, _Capture, _WindowsJob


FIXTURE = Path(__file__).parent / "fixtures" / "process_fixture.py"
PYTHON = Path(sys._base_executable).resolve().as_posix()
WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Windows enforcement tests")


def invocation(tmp_path, mode="echo", args=(), **changes):
    return ProcessInvocation(**{
        "argv": (PYTHON, "-B", "-I", str(FIXTURE.resolve()), mode, *args),
        "stdin": "", "cwd": tmp_path.resolve().as_posix(), "environment": {"LANG": "C"},
        "timeout_seconds": 15, **changes,
    })


@WINDOWS
def test_exact_argv_stdin_cwd_env_and_no_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERO_TEST_SECRET_TOKEN", "synthetic-secret-not-to-inherit")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-not-to-inherit")
    monkeypatch.setenv("PATH", "ambient-not-to-inherit")
    args = ("a b", 'quoted"text', "&", "|", "%ZERO_TEST_SECRET_TOKEN%", "$HOME", "a;b", "\u20ac")
    request = invocation(tmp_path, args=args, stdin="exact\r\nUTF-8 \u20ac \U0001f642\n")
    outcome = LocalProcessRunner().run(request)
    assert outcome.state == "EXITED" and outcome.exit_code == 0
    decoded = json.loads(outcome.stdout)
    assert decoded["args"] == list(args)
    assert decoded["stdin"] == request.stdin and decoded["cwd"] == request.cwd
    assert decoded["env"].get("LANG") == "C"
    # Windows may synthesize SYSTEMROOT even with a custom environment block.
    assert set(decoded["env"]) <= {"LANG", "SYSTEMROOT"}, "unexpected environment names"
    assert "synthetic-secret-not-to-inherit" not in outcome.stdout
    assert "synthetic-key-not-to-inherit" not in outcome.stdout
    assert not hasattr(request, "shell")
    with pytest.raises(FrozenInstanceError):
        request.argv = ("other",)
    with pytest.raises(TypeError):
        request.environment["LANG"] = "changed"


@WINDOWS
@pytest.mark.parametrize("code", [0, 7])
def test_exit_codes(tmp_path, code):
    result = LocalProcessRunner().run(invocation(tmp_path, "exit", (str(code),)))
    assert result.state == "EXITED" and result.exit_code == code
    assert result.started_at <= result.finished_at
    with pytest.raises(FrozenInstanceError):
        result.exit_code = 99


@WINDOWS
def test_bounded_concurrent_streaming(tmp_path, monkeypatch):
    seen = []
    original = _Capture.drain

    def measured(capture, stream):
        class Reader:
            def read(self, amount):
                assert amount <= 8192
                assert len(capture.data) <= capture.limit
                return stream.read(amount)

            def close(self):
                stream.close()
        original(capture, Reader())
        seen.append((len(capture.data), capture.limit))

    monkeypatch.setattr(_Capture, "drain", measured)
    result = LocalProcessRunner().run(invocation(tmp_path, "flood", stdout_limit_bytes=1000, stderr_limit_bytes=700))
    assert result.exit_code == 0
    assert result.stdout == "o" * 1000 and result.stderr == "e" * 700
    assert result.stdout_truncated and result.stderr_truncated
    assert sorted(seen) == [(700, 700), (1000, 1000)]


@WINDOWS
def test_record_caps_apply_to_large_requested_limits(tmp_path):
    result = LocalProcessRunner().run(invocation(tmp_path, "flood", stdout_limit_bytes=1000000,
                                                stderr_limit_bytes=1000000))
    assert result.exit_code == 0
    assert len(result.stdout) == 65536 and len(result.stderr) == 4096
    assert result.stdout_truncated and result.stderr_truncated


@WINDOWS
def test_blocked_stdin_writer_does_not_block_timeout(tmp_path):
    pid_file = tmp_path / "child.pid"
    result = LocalProcessRunner().run(invocation(tmp_path, "sleep", (str(pid_file),),
                                                stdin="x" * 1000000, timeout_seconds=2))
    assert result.state == "TIMEOUT"
    assert_dead(int(pid_file.read_text(encoding="ascii")))


@WINDOWS
def test_job_assignment_failure_never_runs_child_code(tmp_path, monkeypatch):
    def unsupported(self, process):
        raise RunnerError("UNSUPPORTED")
    monkeypatch.setattr(_WindowsJob, "assign_and_resume", unsupported)
    marker = tmp_path / "must-not-exist.pid"
    with pytest.raises(RunnerError, match="^UNSUPPORTED$"):
        LocalProcessRunner().run(invocation(tmp_path, "sleep", (str(marker),)))
    assert not marker.exists()


@WINDOWS
@pytest.mark.parametrize("limit,expected,truncated", [(100, "A\u20ac\U0001f642Z", False),
                                                       (5, "A\u20ac", True), (9, "A\u20ac\U0001f642Z", False)])
def test_utf8_split_chunks(tmp_path, limit, expected, truncated):
    result = LocalProcessRunner().run(invocation(tmp_path, "utf8", stdout_limit_bytes=limit))
    assert result.stdout == expected and result.stdout_truncated is truncated


@WINDOWS
def test_invalid_utf8_fails_closed(tmp_path):
    with pytest.raises(RunnerError, match="^CAPTURE_FAILED$"):
        LocalProcessRunner().run(invocation(tmp_path, "invalid"))


@WINDOWS
def test_missing_executable(tmp_path):
    file = tmp_path / "missing.exe"
    file.write_bytes(b"not executable")
    request = invocation(tmp_path, argv=(file.as_posix(),))
    file.unlink()
    assert LocalProcessRunner().run(request).state == "MISSING_EXECUTABLE"


@WINDOWS
def test_real_startup_failure(tmp_path):
    file = tmp_path / "invalid.exe"
    file.write_bytes(b"not a PE executable")
    with pytest.raises(RunnerError, match="^STARTUP_FAILED$"):
        LocalProcessRunner().run(invocation(tmp_path, argv=(file.as_posix(),)))


@WINDOWS
def test_permission_failure_sanitized(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("sensitive prompt/password=synthetic" * 1000)
    monkeypatch.setattr(subprocess, "Popen", denied)
    with pytest.raises(RunnerError) as error:
        LocalProcessRunner().run(invocation(tmp_path))
    assert str(error.value) == "STARTUP_FAILED" and error.value.__cause__ is None


@WINDOWS
def test_launch_invariants_and_snapshot(tmp_path, monkeypatch):
    original = subprocess.Popen
    source = {"LANG": "C"}
    request = invocation(tmp_path, "exit", ("0",), environment=source)
    source["LANG"] = "mutated"
    calls = []

    def checked(argv, **kwargs):
        assert type(argv) is tuple
        assert argv == request.argv and kwargs["executable"] == request.argv[0]
        assert kwargs["shell"] is False and kwargs["cwd"] == request.cwd
        assert kwargs["env"] == {"LANG": "C"} and type(kwargs["env"]) is dict
        assert kwargs["creationflags"] & 4  # suspended before job assignment
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        calls.append(True)
        return original(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", checked)
    assert LocalProcessRunner().run(request).exit_code == 0
    assert calls == [True]
    with pytest.raises(RunnerError, match="^INVALID_INVOCATION$"):
        LocalProcessRunner().run("python -c unsafe")
    with pytest.raises(ValueError):
        replace(request, argv="not a tuple")


@WINDOWS
def test_deleted_cwd_has_no_fallback(tmp_path):
    root = tmp_path / "cwd"
    root.mkdir()
    request = invocation(root)
    root.rmdir()
    with pytest.raises(RunnerError, match="^INVALID_INVOCATION$"):
        LocalProcessRunner().run(request)


def open_process(pid):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
    if not handle:
        assert ctypes.get_last_error() == 87, "process inspection failed"
    return api, handle


def assert_dead(pid):
    api, handle = open_process(pid)
    if handle:
        try:
            assert api.WaitForSingleObject(handle, 0) == 0, "fixture process still alive"
        finally:
            api.CloseHandle(handle)


@WINDOWS
@pytest.mark.parametrize("cancel", [False, True])
def test_child_timeout_and_cancellation(tmp_path, cancel):
    event = threading.Event()
    pid_file = tmp_path / "child.pid"
    errors = []

    def cancel_after_started():
        deadline = time.monotonic() + 10
        while not pid_file.exists():
            if time.monotonic() > deadline:
                errors.append("fixture never started")
                return
            time.sleep(0.01)
        event.set()

    worker = threading.Thread(target=cancel_after_started) if cancel else None
    if worker:
        worker.start()
    result = LocalProcessRunner(event).run(invocation(tmp_path, "sleep", (str(pid_file),), timeout_seconds=2))
    if worker:
        worker.join(12)
    assert not errors
    assert result.state == ("CANCELLED" if cancel else "TIMEOUT")
    assert_dead(int(pid_file.read_text(encoding="ascii")))


@WINDOWS
@pytest.mark.parametrize("mode", ["timeout", "cancel", "orphan"])
def test_entire_tree_is_dead_before_return(tmp_path, mode):
    event = threading.Event()
    observed = []
    errors = []

    def monitor():
        try:
            deadline = time.monotonic() + 10
            while not (tmp_path / "ready").exists():
                if time.monotonic() >= deadline:
                    raise AssertionError("tree not ready")
                time.sleep(0.005)
            if mode != "orphan":
                for name in ("root", "branch", "leaf"):
                    api, handle = open_process(int((tmp_path / (name + ".pid")).read_text(encoding="ascii")))
                    assert handle and api.WaitForSingleObject(handle, 0) == 0x102, "fixture was not alive"
                    observed.append((api, handle))
            if mode == "cancel":
                event.set()
        except Exception:
            errors.append("tree observation failed")
            event.set()

    watcher = threading.Thread(target=monitor)
    watcher.start()
    try:
        result = LocalProcessRunner(event).run(invocation(
            tmp_path, "orphan" if mode == "orphan" else "tree", (str(tmp_path),), timeout_seconds=3))
        watcher.join(12)
        assert not watcher.is_alive() and not errors
        assert result.state == {"timeout": "TIMEOUT", "cancel": "CANCELLED", "orphan": "EXITED"}[mode]
        for api, handle in observed:
            assert api.WaitForSingleObject(handle, 0) == 0, "descendant still alive after return"
        for name in ("root", "branch", "leaf"):
            assert_dead(int((tmp_path / (name + ".pid")).read_text(encoding="ascii")))
    finally:
        watcher.join(12)
        for api, handle in observed:
            api.CloseHandle(handle)


@WINDOWS
def test_cleanup_failure_raises_and_kill_on_close_cleans_tree(tmp_path, monkeypatch):
    def failed_wait(self):
        raise OSError("external sensitive details")
    monkeypatch.setattr(_WindowsJob, "terminate_and_wait", failed_wait)
    with pytest.raises(RunnerError, match="^CLEANUP_FAILED$"):
        LocalProcessRunner().run(invocation(tmp_path, "tree", (str(tmp_path),), timeout_seconds=2))
    # Failure never claims cleanup succeeded. Verify kill-on-close fallback too.
    for name in ("root", "branch", "leaf"):
        pid = int((tmp_path / (name + ".pid")).read_text(encoding="ascii"))
        api, handle = open_process(pid)
        if handle:
            try:
                assert api.WaitForSingleObject(handle, 5000) == 0
            finally:
                api.CloseHandle(handle)


@WINDOWS
def test_pre_cancel_never_starts(tmp_path, monkeypatch):
    event = threading.Event()
    event.set()
    def forbidden(*args, **kwargs):
        raise AssertionError("must not start")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert LocalProcessRunner(event).run(invocation(tmp_path)).state == "CANCELLED"


def test_other_platform_fails_closed(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(os, "name", "posix")
        with pytest.raises(RunnerError, match="^UNSUPPORTED$"):
            LocalProcessRunner().run(None)


def test_import_is_inert(tmp_path):
    script = r'''
import sys, os, ctypes, threading, subprocess, time, dataclasses, typing
from ctypes import wintypes
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
import zero_core.process_runner
assert "zero_core.config" not in sys.modules
assert "zero_core.engineering" not in sys.modules
print("INERT")
'''
    result = subprocess.run([PYTHON, "-B", "-c", script, str(Path(__file__).resolve().parents[2])],
                            capture_output=True, cwd=tmp_path, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "INERT"
    assert not list(tmp_path.iterdir())
