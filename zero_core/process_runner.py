"""Windows local process port. No adapters, permission policy or global resources.

Unsupported/startup/capture/cleanup failures raise fixed-message RunnerError;
the existing G2A boundary maps these to FAILED without exposing details.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, replace
import os
import subprocess
import threading
import time
from typing import Protocol

from zero_core.engineering_execution import ProcessInvocation, ProcessOutcome, canonical_path
from zero_core.engineering_contracts import utc_now


class RunnerError(RuntimeError):
    """Fixed diagnostic codes only; never include external exception text."""

    def __init__(self, code: str):
        if code not in {"UNSUPPORTED", "INVALID_INVOCATION", "STARTUP_FAILED", "CLEANUP_FAILED", "CAPTURE_FAILED"}:
            code = "STARTUP_FAILED"
        self.code = code
        super().__init__(code)


class Cancellation(Protocol):
    def is_set(self) -> bool: ...


class _Limits(ctypes.Structure):
    _fields_ = [("user_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD)]


class _IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _Limits), ("io", _IO), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [("user", ctypes.c_longlong), ("kernel", ctypes.c_longlong),
                ("period_user", ctypes.c_longlong), ("period_kernel", ctypes.c_longlong),
                ("faults", wintypes.DWORD), ("total", wintypes.DWORD),
                ("active", wintypes.DWORD), ("terminated", wintypes.DWORD)]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                ("thread_id", wintypes.DWORD), ("process_id", wintypes.DWORD),
                ("priority", wintypes.LONG), ("delta", wintypes.LONG), ("flags", wintypes.DWORD)]


class _ProcessIds(ctypes.Structure):
    _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                ("ids", ctypes.c_size_t * 256)]


class _WindowsJob:
    """All handles are per-run. No breakaway flags and no inheritable job handle."""

    def __init__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        H, D, B, P = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p
        signatures = {
            "CreateJobObjectW": ([P, wintypes.LPCWSTR], H),
            "SetInformationJobObject": ([H, ctypes.c_int, P, D], B),
            "QueryInformationJobObject": ([H, ctypes.c_int, P, D, P], B),
            "AssignProcessToJobObject": ([H, H], B),
            "TerminateJobObject": ([H, wintypes.UINT], B),
            "CloseHandle": ([H], B),
            "CreateToolhelp32Snapshot": ([D, D], H),
            "Thread32First": ([H, ctypes.POINTER(_ThreadEntry)], B),
            "Thread32Next": ([H, ctypes.POINTER(_ThreadEntry)], B),
            "OpenThread": ([D, B, D], H),
            "ResumeThread": ([H], D),
            "OpenProcess": ([D, B, D], H),
            "WaitForSingleObject": ([H, D], D),
            "IsProcessInJob": ([H, H, ctypes.POINTER(B)], B),
        }
        for name, (arguments, result) in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = arguments, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise RunnerError("UNSUPPORTED")
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
        limits.basic.active_limit = 256
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise RunnerError("UNSUPPORTED")

    def assign_and_resume(self, process):
        # CPython retains the process handle but closes the primary thread
        # handle. Discover the single suspended primary thread using Win32 APIs.
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise RunnerError("UNSUPPORTED")
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise RunnerError("STARTUP_FAILED")
        try:
            entry = _ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = []
            ok = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while ok:
                if entry.process_id == process.pid:
                    found.append(entry.thread_id)
                entry.size = ctypes.sizeof(entry)
                ok = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != 18 or len(found) != 1:  # ERROR_NO_MORE_FILES
                raise RunnerError("STARTUP_FAILED")
            thread = self.api.OpenThread(2, False, found[0])  # THREAD_SUSPEND_RESUME
            if not thread:
                raise RunnerError("STARTUP_FAILED")
            try:
                if self.api.ResumeThread(thread) != 1:
                    raise RunnerError("STARTUP_FAILED")
            finally:
                if not self.api.CloseHandle(thread):
                    raise RunnerError("CLEANUP_FAILED")
        finally:
            if not self.api.CloseHandle(snapshot):
                raise RunnerError("CLEANUP_FAILED")

    def active(self):
        info = _Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise RunnerError("CLEANUP_FAILED")
        return info.active

    def terminate_and_wait(self):
        handles = []
        try:
            members = _ProcessIds()
            if not self.api.QueryInformationJobObject(self.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None):
                raise RunnerError("CLEANUP_FAILED")
            if members.count != members.assigned or members.count > 256:
                raise RunnerError("CLEANUP_FAILED")
            for pid in members.ids[:members.count]:
                handle = self.api.OpenProcess(0x100000 | 0x1000, False, pid)
                if not handle:
                    if ctypes.get_last_error() == 87:  # already exited
                        continue
                    raise RunnerError("CLEANUP_FAILED")
                handles.append(handle)
                member = wintypes.BOOL()
                if not self.api.IsProcessInJob(handle, self.handle, ctypes.byref(member)) or not member.value:
                    raise RunnerError("CLEANUP_FAILED")  # PID reuse/inspection failure
            if not self.api.TerminateJobObject(self.handle, 1):
                raise RunnerError("CLEANUP_FAILED")
            deadline = time.monotonic() + 5
            while self.active():
                if time.monotonic() >= deadline:
                    raise RunnerError("CLEANUP_FAILED")
                time.sleep(0.01)
            for handle in handles:
                milliseconds = max(0, int((deadline - time.monotonic()) * 1000))
                if self.api.WaitForSingleObject(handle, milliseconds) != 0:
                    raise RunnerError("CLEANUP_FAILED")
        finally:
            close_failed = False
            for handle in handles:
                if not self.api.CloseHandle(handle):
                    close_failed = True
            if close_failed:
                raise RunnerError("CLEANUP_FAILED")

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise RunnerError("CLEANUP_FAILED")
            self.handle = None


class _Capture:
    """Retain at most limit bytes; each temporary read is at most 8192 bytes."""

    def __init__(self, limit):
        self.limit = limit
        self.data = bytearray()
        self.truncated = False
        self.failed = False

    def drain(self, stream):
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                remaining = self.limit - len(self.data)
                self.data.extend(chunk[:remaining])
                self.truncated |= len(chunk) > remaining
        except Exception:
            self.failed = True
        finally:
            try:
                stream.close()
            except Exception:
                self.failed = True

    def text(self):
        # Decode only once across arbitrary read boundaries. If truncation splits
        # a UTF-8 character, omit that incomplete suffix, never insert corruption.
        import codecs
        try:
            return codecs.getincrementaldecoder("utf-8")("strict").decode(
                bytes(self.data), final=not self.truncated)
        except UnicodeError:
            raise RunnerError("CAPTURE_FAILED") from None


@dataclass(frozen=True)
class LocalProcessRunner:
    """Cancellation is injected once, outside the unchanged run(invocation) port.

    Windows CPython only. Other platforms fail before allocating resources.
    Windows termination is forced job-wide; no unreliable console signal grace.
    """

    cancellation: Cancellation | None = None

    def run(self, invocation: ProcessInvocation) -> ProcessOutcome:
        started = utc_now()
        if os.name != "nt":
            raise RunnerError("UNSUPPORTED")
        if type(invocation) is not ProcessInvocation:
            raise RunnerError("INVALID_INVOCATION")
        try:
            executable = canonical_path(invocation.argv[0], directory=False)
        except FileNotFoundError:
            return ProcessOutcome("MISSING_EXECUTABLE", started, utc_now())
        except (OSError, ValueError, TypeError, IndexError):
            raise RunnerError("INVALID_INVOCATION") from None
        try:
            invocation = replace(invocation)  # fresh validated immutable snapshot
            if executable != invocation.argv[0]:
                raise ValueError("canonical executable required")
            stdin_bytes = invocation.stdin.encode("utf-8", "strict")
        except (OSError, ValueError, TypeError):
            raise RunnerError("INVALID_INVOCATION") from None
        if self.cancellation is not None and self.cancellation.is_set():
            return ProcessOutcome("CANCELLED", started, utc_now())

        process = None
        job = None
        threads = []
        failure = None
        state = "EXITED"
        stdout = _Capture(min(invocation.stdout_limit_bytes, 65536))
        stderr = _Capture(min(invocation.stderr_limit_bytes, 4096))
        writer_failed = []
        deadline = time.monotonic() + invocation.timeout_seconds
        try:
            job = _WindowsJob()
            try:
                process = subprocess.Popen(
                    invocation.argv, executable=invocation.argv[0], shell=False,
                    cwd=invocation.cwd, env=dict(invocation.environment),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    bufsize=0, close_fds=True,
                    creationflags=0x4 | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                )  # CREATE_SUSPENDED: cannot spawn descendants before job assignment
            except FileNotFoundError:
                # Cwd races must not be misreported as missing executable.
                try:
                    canonical_path(invocation.argv[0], directory=False)
                except FileNotFoundError:
                    state = "MISSING_EXECUTABLE"
                else:
                    raise RunnerError("STARTUP_FAILED") from None
            if process is not None:
                job.assign_and_resume(process)

                def write_stdin():
                    try:
                        view = memoryview(stdin_bytes)
                        while view:
                            written = process.stdin.write(view[:8192])
                            if not written:
                                raise OSError("closed stdin")
                            view = view[written:]
                    except BrokenPipeError:
                        # A program may intentionally close stdin early.
                        pass
                    except Exception:
                        writer_failed.append(True)
                    finally:
                        try:
                            process.stdin.close()
                        except Exception:
                            writer_failed.append(True)

                for target, args in ((stdout.drain, (process.stdout,)),
                                     (stderr.drain, (process.stderr,)), (write_stdin, ())):
                    worker = threading.Thread(target=target, args=args, daemon=True)
                    worker.start()
                    threads.append(worker)
                while True:
                    if self.cancellation is not None and self.cancellation.is_set():
                        state = "CANCELLED"
                        break
                    if process.poll() is not None:
                        break
                    if time.monotonic() >= deadline:
                        state = "TIMEOUT"
                        break
                    time.sleep(0.01)
        except RunnerError as exc:
            failure = exc.code
        except Exception:
            failure = "STARTUP_FAILED"
        finally:
            # Also reap orphan descendants on normal root exit. Never report an
            # outcome while processes in our job remain alive.
            if job is not None:
                try:
                    job.terminate_and_wait()
                except Exception:
                    failure = "CLEANUP_FAILED"
                finally:
                    try:
                        job.close()  # kill-on-close fallback even after failed wait
                    except Exception:
                        failure = "CLEANUP_FAILED"
            if process is not None:
                try:
                    if process.poll() is None:
                        process.kill()  # assignment may have failed while suspended
                    process.wait(timeout=5)
                except Exception:
                    failure = "CLEANUP_FAILED"
                for worker in threads:
                    worker.join(timeout=5)
                    if worker.is_alive():
                        failure = "CLEANUP_FAILED"
                if not any(worker.is_alive() for worker in threads):
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        try:
                            pipe.close()
                        except Exception:
                            failure = "CLEANUP_FAILED"
                # CPython Popen owns this handle; Close is idempotent.
                try:
                    process._handle.Close()
                except Exception:
                    failure = "CLEANUP_FAILED"
        if failure:
            raise RunnerError(failure) from None
        if stdout.failed or stderr.failed or writer_failed:
            raise RunnerError("CAPTURE_FAILED")
        return ProcessOutcome(
            state=state, exit_code=process.returncode if state == "EXITED" else None,
            stdout=stdout.text(), stderr=stderr.text(),
            stdout_truncated=stdout.truncated, stderr_truncated=stderr.truncated,
            started_at=started, finished_at=max(started, utc_now()),
        )
