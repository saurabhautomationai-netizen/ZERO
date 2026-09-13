# G3: independent local verification and evidence

ZERO owns verification. Executors report attempts only. This additive module
does not modify G1/G2, activate Codex or Goose, approve work, classify risk, execute
engineering work, modify project state, persist checkpoints or complete milestones.
Approved verification commands are distinct from engineering work and run only
through the injected G2 `ProcessRunner` contract.

## Trusted application boundary

`TrustedVerificationConfiguration` is immutable application input, outside the
TaskPacket. It pins project, task, execution ID, canonical existing root, exact
allowed observation paths, exact required changes and approved commands. It also
sets file-count, file-size, snapshot-size, evidence-size and output-evidence limits,
and whether deletion is permitted. Empty requirement/command sets together are
rejected. Paths are normalized with G1 rules; duplicate and case-fold aliases are
rejected on every host. Root resolution uses G2's canonical path checks.

`IndependentVerifier.capture_pre` creates a snapshot through the injected observer
and clock before execution. The verifier retains that exact snapshot in memory.
It also retains its original integrity digest to detect in-memory tampering.
`verify` accepts only a snapshot captured by that verifier instance, with matching
project/root/task/attempt and packet/policy/decision/configuration fingerprints.
G1 decision and execution binding validators are explicitly called. Pre observation
must precede the reported execution start; post observation must follow its finish.
The trusted application must control lifecycle ordering, clock, policy/configuration,
observer and runner injection. Worker-provided services or snapshots are not trusted.
The in-memory reference check is not authentication, durable storage or replay defense.

Malformed configuration or binding raises fixed-code `VerificationError` with
BLOCKED verdict before a correctly bound evidence record can be made. No existing
G1/G2 outcome record is changed. Executor summaries, reported file lists and reported
test counts never enter the change comparison or determine its verdict. The complete
execution record is fingerprinted solely to bind evidence to that exact attempt.

## Observation scope and conservative coverage

The real `LocalWorkspaceObserver` is read-only. It lists the root and recurses only
into directory ancestors of exact trusted observation paths. It never recurses into
other branches, including opaque held/runtime branches. Unapproved direct entries
receive bounded metadata only; their contents are never opened or hashed. New,
deleted or metadata-changed unapproved entries produce unexpected-change failure.
An existing unapproved file or opaque directory is a coverage gap even when its
metadata is unchanged: its unseen contents may have changed. Such a gap produces
INCONCLUSIVE, never VERIFIED. Nothing cleans or restores unexpected paths.

This is deliberately restrictive: a real repository with opaque `.git`, runtime,
held or other unobserved branches cannot receive whole-workspace VERIFIED from
this local observer. Metadata alone cannot prove those branches unchanged. Supply
an appropriately scoped, fully observable isolated workspace for affirmative G3
verification. Do not broaden the allowlist to prohibited files merely to get a
green verdict. Git/status evidence is explicitly deferred; no Git subprocess,
diff parsing, repository cleanup or clean-repository requirement is implemented.
The implementation and tests do not observe the live ZERO workspace as G3 input.

File count includes listed directory entries and absent configured paths. The
entire bounded inventory is collected before content hashing. Eligible files must
be regular and within the configured size limit before opening; reads are bounded
to that limit plus one byte to detect growth. Evidence contains only relative paths,
type/state, size, fixed metadata tuples and SHA-256 digests, never file contents.
Paths and entries are sorted deterministically. Directories, devices, pipes, sockets,
symlinks, junctions and reparse points are never read as regular-file content.

On Windows, opening uses CreateFile with OPEN_REPARSE_POINT, read-only access and
read sharing only. The handle's final path must match the trusted target before
any content read. Root/parent chains are checked for links/reparse points; pre-open,
opened-handle, post-read and final-path metadata must agree. Identity, type, size,
mtime and explicit birth time are compared. Using birth time avoids inconsistent
Windows ctime creation/change semantics between path and handle APIs observed in
testing. Python documents the Windows ctime transition and explicit birth time in
its [stat result documentation](https://docs.python.org/3/library/os.html#os.stat_result).
Directory enumeration likewise pins a no-follow directory handle, rejects reparse
attributes with [GetFileInformationByHandleEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex),
and checks the handle's final path before listing names. These handles are created
only while observing, never during module import.

POSIX uses directory-descriptor-relative O_NOFOLLOW opens and O_NONBLOCK for the
final target. Missing no-follow support fails closed. The validated platform for
this delivery is Windows; G2B still refuses POSIX process execution. No POSIX
end-to-end execution claim is made.

Directory metadata is checked during and after inventory; eligible file metadata
is rechecked after hashing. Replacement, mutation or unstable observation cannot
verify. Snapshots are bounded observations, not atomic filesystem transactions:
no guarantee covers a malicious actor restoring all metadata between reads,
unobserved areas, or changes after observation completes. No hostile-code sandbox,
filesystem freeze, authorization boundary or total historical change journal is
claimed. Concurrent writers should be excluded by trusted application orchestration.

## Evidence and command semantics

Frozen records cover binding, file observations, snapshots, change sets, individual
test evidence and aggregate verification evidence. Command records contain a G2
`ProcessInvocation`: exact argv tuple, canonical cwd, immutable explicit environment,
stdin and timeout/output limits. There is no shell field or shell command string.
The complete requested command tuple must structurally equal the trusted command
tuple before any runner call; changed IDs, ordering, argv, cwd, environment, stdin
or limits block with zero calls. TaskPacket commands are never used to select tests.

All required commands must pass. A zero exit supports only that approved command's
successful exit, not test-case counts or task completion. G3 intentionally provides
no prose test-count parser. Nonzero exit fails even if output is truncated. Timeout,
cancellation and missing executable block. Truncated/oversized successful output is
INCONCLUSIVE. Startup, cleanup and other runner exceptions block with a fixed short
summary and no external exception text. Actual ProcessOutcome state, exit code,
timestamps, truncation flags and bounded output-prefix hashes are recorded. Raw
stdout/stderr, prompts, argv and environment values are not copied into evidence.
Output-digest limits are explicit in the bound trusted configuration.

The workspace is observed again after verification commands; a command-induced
change or loss of observation stability blocks. The final change set corresponds
to the final post-snapshot digest. Tests must be provisioned to avoid writing into
the observed workspace. G2B owns subprocess timeout, cancellation, environment and
process-tree enforcement; the verifier never invokes a subprocess directly.

An expected MODIFIED file requires an independently changed content digest.
Rewriting identical content or merely touching metadata does not satisfy it.
Observed metadata changes still appear in the change set and can fail unexpected
change checks. Approved deletion requires both an expected deletion and the trusted
deletion flag. Snapshot comparison is the sole source of created/modified/deleted
and unchanged paths; worker file claims are ignored.
Structural ancestor directories of expected files are implicitly permitted in the
change comparison; opaque unrelated directories are never treated as such ancestors.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| VERIFIED | Exact binding, stable complete observations, required content changes, no unexpected/prohibited changes and every required command succeeded with complete bounded output |
| FAILED | A requirement is observably unmet: missing required change, unexpected change, prohibited deletion or nonzero approved-command exit |
| BLOCKED | Invalid binding/configuration/command, missing root/executable, security ambiguity, unsupported file, resource limit, runner failure or test-induced mutation |
| INCONCLUSIVE | Race, unstable/unavailable observation, opaque coverage gap or incomplete successful-command output |

When multiple findings coexist, precedence is BLOCKED, FAILED, INCONCLUSIVE,
VERIFIED. Tests are not launched when existing observations already preclude
verification. Uncertainty never becomes VERIFIED. The word VERIFIED concerns
these local configured facts only; it is not completion of a task or milestone.

## Integrity, ownership and remaining phases

The complete evidence payload, including schema version, all binding digests,
pre/post digests, observed changes, test facts, reasons, verdict and injected UTC
creation time, is canonicalized with sorted JSON keys and compact separators.
SHA-256 produces a deterministic integrity fingerprint. The record explicitly
labels it `SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED`. It is not a signature, proof
of origin, authentication or replay prevention. Reconstructing records with
different verdict-relevant fields changes that fingerprint. Constructors reject
duplicate observations/command IDs, invalid versions and contradictory success
test records. Evidence-size overflow produces compact BLOCKED evidence.

The trusted application must keep credentials out of file names, task/config IDs
and command configuration. G3 does not accept or discover credentials. It neither
logs raw streams/content nor stores evidence on disk. The in-memory snapshots and
evidence returned to the caller have no durable recovery semantics.

- G4 owns durable evidence persistence, checkpoints and recovery.
- G5 owns independent reviewer/Antigravity review.
- G6 owns unattended queues under established application gates.
- Authenticated HITL remains a separate authoritative integration.
- Codex and Goose remain inactive, replaceable adapters. ZERO remains the source
  of truth for verification and later lifecycle decisions.

## Isolated validation

```text
python -B -m pytest --confcutdir=tests/g1_contracts -p no:cacheprovider tests/g1_contracts -q
python -B -m pytest --confcutdir=tests/g2_executors -p no:cacheprovider tests/g2_executors/test_execution_boundary.py -q
python -B -m pytest --confcutdir=tests/g2_executors -p no:cacheprovider tests/g2_executors/test_process_runner.py -q
python -B -m pytest --confcutdir=tests/g3_verification -p no:cacheprovider tests/g3_verification/test_verification.py -q
```

Unit tests use temporary directories, fake runners and fake clocks. One harmless
read-only Python fixture runs through G2B on Windows. Import checks preload existing
G1/G2A dependencies and guard G3 import against writes, processes, network, environment
reads and DLL allocation. Preservation hashes for live pre-existing dirty files are
an out-of-band maintenance check only, kept in memory and never G3 evidence.
