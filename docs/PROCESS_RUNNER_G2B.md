# G2B: Windows local process runner

`LocalProcessRunner` implements the existing `run(ProcessInvocation)` port without
changing G2A. Only the concrete frozen invocation class is accepted. The runner
revalidates and snapshots the invocation, requires canonical argv[0], and passes
an argv tuple, explicit executable, exact cwd, a fresh explicit environment dict
and `shell=False` to `subprocess.Popen`. Shell use is not caller-configurable.
There is no PATH search, cwd fallback or parent-environment merge.

The runner does not activate Codex or Goose, inspect CLI output schemas, classify
risk or grant permission. Application use remains beneath G2A's exact LOW_RISK
gate. Direct runner use is a trusted application capability, not a permission API.
G2A adapters remain blocked. No operational ZERO runtime integration is added.

## Windows lifetime enforcement

The implementation uses Windows CPython and standard-library ctypes. Every run
allocates an unnamed, non-inheritable Job Object with kill-on-job-close and a
256-active-process cap. Neither breakaway flag is enabled. The child starts with
CREATE_SUSPENDED, CREATE_NEW_PROCESS_GROUP and CREATE_NO_WINDOW. Job assignment
must succeed before the initial thread resumes. CPython closes the original thread
handle, so the runner uses a Toolhelp thread snapshot, requires exactly one owned
thread, and resumes it through an explicit thread handle. Failed assignment or
unsupported job nesting kills and waits for the still-suspended child.

Timeout uses a monotonic deadline; cancellation uses an injected object exposing
`is_set()`, such as `threading.Event`. Cancellation takes precedence at polling
boundaries. A pre-set event returns CANCELLED without launching. Polling is every
10 ms; scheduling and OS calls add latency. Windows CreateProcess is synchronous
and cannot itself be interrupted by this Python polling loop.

Cleanup uses forced `TerminateJobObject` directly. Windows console signals are
not a reliable graceful shutdown mechanism for hidden processes, so there is no
pretend graceful interval. The runner snapshots job members, retains process
handles, terminates the job, checks active membership reaches zero, and waits for
the retained process handles to signal termination. PID membership checks reject
reuse/inspection ambiguity. Root waiting and stream-thread joining happen before
an outcome is returned. Cleanup also runs on normal root exit to remove orphan
descendants. Job close is a kill-on-close fallback if explicit termination fails.
Failure to confirm cleanup raises CLEANUP_FAILED instead of returning TIMEOUT,
CANCELLED or a successful exit. A failure is not a claim that every process died.

The fixture suite observes a live parent, child and grandchild through OS process
handles, then requires those same handles to be signaled immediately after timeout
or cancellation returns. It separately tests orphan cleanup after normal root exit
and a failed-cleanup path using the kill-on-close fallback. Job accounting alone
proved insufficient in initial testing: zero active processes could precede
signaled process handles. The retained-handle waits address that tested gap.

This is local process lifetime containment, not a hostile-code security sandbox.
It does not restrict filesystem effects, registry, credentials, privileges or
network, and does not control work delegated to independent services. Job-member
snapshots are not an atomic census of adversarial concurrent process creation;
the kernel Job Object terminates its members, while explicit handle waits cover
members observed at cleanup. No claim of adversarial spawn-race verification is
made. Trusted executable provisioning and filesystem TOCTOU protection remain
separate requirements. No executable identity hash is pinned by G2B.

POSIX and other platforms explicitly raise UNSUPPORTED before process allocation.
There is no untested POSIX subprocess fallback. A later POSIX implementation must
create a new session and test group TERM/KILL cleanup before support is enabled.

## Streams, encoding and immutable results

Two concurrent reader threads drain stdout and stderr in chunks of at most 8192
bytes. Each retains at most its requested byte limit, further capped at G2A's
65536/4096 stdout/stderr record capacities. Excess bytes continue to drain and
set the corresponding truncation flag. No `communicate()` or full-output buffer
is used. A separate writer prevents large stdin from blocking capture or timeout.
Input is explicitly UTF-8, written as bytes with partial-write handling. Closing
stdin early is allowed; the runner does not claim that a process consumed it.

Retained output is decoded as strict UTF-8 across read boundaries. A truncated
partial character at the retained suffix is omitted and the truncation flag stays
true. Malformed UTF-8 fails closed as CAPTURE_FAILED. Output remains untrusted;
the runner does not interpret it as file/test evidence. It never logs output or
environment. Real child output can itself contain sensitive text, so callers must
not persist raw streams as trusted summaries. No secrets are supplied by G2B.

The invocation environment remains G2A's closed non-secret allowlist. Windows or
its runtime may synthesize SYSTEMROOT in a child environment even when omitted
from the supplied environment block; the fixture permits only that additional
name. Synthetic secret-like parent variables and PATH must be absent. Fixtures
use Python `-B -I`, so they do not write bytecode or load user Python configuration.

ProcessOutcome remains the existing frozen record with UTC start/end times:

| Condition | Port result |
| --- | --- |
| Completed, zero or nonzero exit | EXITED with actual exit code |
| Executable disappeared | MISSING_EXECUTABLE, no exit code |
| Timeout after confirmed cleanup | TIMEOUT, no exit code |
| Cancellation after confirmed cleanup, or before launch | CANCELLED, no exit code |
| Unsupported platform/job enforcement | RunnerError: UNSUPPORTED |
| Invalid invocation/cwd/environment | RunnerError: INVALID_INVOCATION |
| Permission/invalid executable/startup failure | RunnerError: STARTUP_FAILED |
| Stream failure or malformed encoding | RunnerError: CAPTURE_FAILED |
| Unconfirmed process/handle/pipe cleanup | RunnerError: CLEANUP_FAILED |

These exception codes are fixed, short and contain no external exception message,
traceback, environment, stdin or task prompt. No new outcome states are invented.
G2A already maps runner exceptions to FAILED with a fixed summary. It maps missing
executable to BLOCKED. A direct caller can distinguish UNSUPPORTED using the error
code. Deterministic mapping does not imply reproducible process times or output.

## Validation and scope

Only these isolated suites are used, with bytecode and pytest cache disabled:

```text
python -B -m pytest --confcutdir=tests/g1_contracts -p no:cacheprovider tests/g1_contracts -q
python -B -m pytest --confcutdir=tests/g2_executors -p no:cacheprovider tests/g2_executors/test_execution_boundary.py -q
python -B -m pytest --confcutdir=tests/g2_executors -p no:cacheprovider tests/g2_executors/test_process_runner.py -q
```

Tests use only a harmless local Python fixture. The import test preloads existing
G1/G2A dependencies, then guards G2B import against environment reads, writes,
processes, network and DLL/resource allocation. There are no global job handles.

G2B PASS requires actual local execution, bounded concurrent streaming, timeout
cleanup and demonstrated process-tree termination on the current Windows host.
It does not mean adapter activation, authenticated HITL, G3 verification, G4 durable
recovery, G5 independent review, G6 unattended queues or autonomous operation.
ZERO remains the authority for those later application decisions.

## Win32 references

- [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)
- [Job process ID list](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list)
- [ResumeThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread)

These references establish API semantics; the local fixture tests establish the
behavior observed on this host. They do not substitute for local cleanup tests.
