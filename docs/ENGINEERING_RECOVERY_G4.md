# G4: durable checkpoints, crash recovery and safe resume planning

ZERO owns recovery state. This additive module does not modify G1/G2/G3, activate
Codex, Goose or Claude, approve work, classify risk, execute engineering work,
verify a workspace, complete milestones or run any command. It persists bounded
lifecycle records and reconstructs a recovery *plan*. Acting on that plan is the
trusted application's job, and any interrupted or uncertain work must be sent
back through G3 before it can be treated as complete.

The central rule: **an interrupted executor is never assumed to have succeeded.**

## Trusted persistence boundary

`TrustedRecoveryConfiguration` is immutable application input, outside the
TaskPacket. It pins:

| Field | Meaning |
| --- | --- |
| `project_id` | the only project this store will bind records to |
| `repository_root` | canonical, existing, link-free workspace root |
| `recovery_directory` | canonical, existing directory that may contain the store |
| `database_path` | canonical database file, required to be inside that directory |
| `schema_version` | exactly `1`; anything else is refused |
| `max_record_bytes` | serialized size ceiling, enforced before any write |
| `durability` | `DurabilityMode.FULL_SYNCHRONOUS_DELETE_JOURNAL`, the only mode |
| `busy_timeout_ms` | bounded wait before contention becomes a `STORE_BUSY` code |
| `retention` | `RetentionPolicy`, which cannot enable automatic deletion |

Roots and the database parent are resolved with G2's `canonical_path`, so a
symlink, junction or reparse point anywhere in the chain is rejected rather than
followed, and a non-canonical or missing path is refused. The database filename
is restricted to a single safe component, the parent must be the trusted recovery
directory or a directory beneath it, and an existing database file must be a plain
regular file. An unsupported platform fails closed.

The store location is **not task-controlled**. `open_recovery_store`,
`RecoveryStore.append`, `RecoveryStore.latest_checkpoint` and
`RecoveryStore.assess` accept no path, filename, URI or schema version. A
TaskPacket, executor output, prompt or external agent cannot reach any of the
fields above. A packet whose `repository_root` or `project_id` disagrees with the
configuration is rejected with `BINDING_INVALID` before anything is written.

Import is inert. No filesystem, environment, network or process access occurs
until a store is explicitly opened; the database is created on that call, never at
import. The module never reads `os.environ`, never opens a socket, never starts a
subprocess and contains no `pickle`, `eval`, `exec` or YAML object construction.

## Schema

Three tables, created together in one transaction:

* `recovery_schema` — one row: schema version, permitted durability mode, creation time.
* `recovery_checkpoint` — `checkpoint_id` primary key, identity columns, `sequence`,
  canonical JSON `payload`, unique `fingerprint`, `previous_fingerprint`,
  `request_digest`, `idempotency_key`; unique on `(project_id, execution_id, sequence)`
  and on `(project_id, execution_id, idempotency_key)`.
* `recovery_event` — `event_id` primary key, identity columns, `sequence`, a
  `checkpoint_id` foreign key, canonical JSON `payload`, unique `fingerprint`,
  `previous_fingerprint`; unique on `(project_id, execution_id, sequence)`.

Every statement is a module constant. No caller value, table name or column name
is ever interpolated into SQL; all values travel as bound parameters, and all
identifiers are validated against `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`, which
rejects NUL bytes, lone surrogates, control characters and oversized input.

On open the schema is validated rather than adapted: the table set must match
exactly, every column list must match exactly, exactly one schema row must exist,
and its version must be `1`. An unknown or newer version raises
`SCHEMA_UNSUPPORTED`; a mismatched table or column set raises `SCHEMA_CORRUPT`.
**There is no automatic migration and nothing is ever dropped, truncated or
rewritten.** Because schema creation is a single transaction, an interrupted first
open rolls back to a file with no tables, which the next open initialises cleanly;
any half-built schema is blocked instead.

## Durability

Each connection sets, and then reads back to confirm, `foreign_keys = ON`,
`journal_mode = DELETE` and `synchronous = FULL`, with the busy timeout supplied to
the driver. If any of them does not take effect, the store refuses to open.

Rollback-journal mode is chosen deliberately. The durable state is one file plus a
transient journal, so a terminated process leaves either the complete old state or
the complete new state, and reopening rolls the journal back. WAL is rejected: it
adds `-wal`/`-shm` sidecars, needs shared memory that some filesystems do not
provide, and moves commit durability into a checkpoint this module does not
control.

The connection runs with `isolation_level=None`, so there is no implicit
autocommit around a multi-record transition. Every transition issues an explicit
`BEGIN IMMEDIATE`, and every read path an explicit `BEGIN DEFERRED`. Any failure
rolls back before the error escapes. Handles are closed deterministically by
`close()`, which is idempotent; a closed store refuses every operation with
`STORE_CLOSED`.

## Immutable records and the transition model

`RecoveryState` has eleven members: `PLANNED`, `EXECUTION_STARTED`,
`EXECUTION_REPORTED`, `VERIFICATION_STARTED`, `VERIFIED`, `FAILED`, `BLOCKED`,
`INCONCLUSIVE`, `INTERRUPTED`, `REQUIRES_REVERIFICATION`, `ABANDONED`.

`LEGAL_TRANSITIONS` is the complete, documented edge set. `None` is the empty
chain, so every chain begins at `PLANNED`:

```
None                    -> PLANNED
PLANNED                 -> EXECUTION_STARTED | ABANDONED
EXECUTION_STARTED       -> EXECUTION_REPORTED | INTERRUPTED | ABANDONED
EXECUTION_REPORTED      -> VERIFICATION_STARTED | REQUIRES_REVERIFICATION
                           | INTERRUPTED | ABANDONED
VERIFICATION_STARTED    -> VERIFIED | FAILED | BLOCKED | INCONCLUSIVE
                           | INTERRUPTED | ABANDONED
VERIFIED                -> REQUIRES_REVERIFICATION | ABANDONED
FAILED / BLOCKED        -> REQUIRES_REVERIFICATION | ABANDONED
INCONCLUSIVE            -> REQUIRES_REVERIFICATION | ABANDONED
INTERRUPTED             -> REQUIRES_REVERIFICATION | ABANDONED
REQUIRES_REVERIFICATION -> VERIFICATION_STARTED | ABANDONED
ABANDONED               -> (terminal)
```

`VERIFIED` is never silently overwritten. Leaving it requires an explicit
`REQUIRES_REVERIFICATION` or `ABANDONED` edge, and a genuinely new attempt uses a
new execution ID and therefore a new chain, so an earlier verified result stays
readable as history. `ABANDONED` is the explicit terminal edge.

A transition is rejected when it skips a required state, leaves an unknown state,
decreases or reuses a sequence number, changes the project, task, execution or
repository binding, replaces a stored packet, policy, decision or attempt
fingerprint, repeats a checkpoint or event ID, or claims `VERIFIED` on an executor
report alone.

`RecoveryCheckpoint` carries the schema version, an injected checkpoint ID,
project/task/execution binding, canonical repository root, a monotonic
per-execution sequence, the previous checkpoint fingerprint, the lifecycle state,
the TaskPacket, WorkspacePolicy and PermissionDecision fingerprints, the executor
attempt fingerprint when applicable, the G3 evidence fingerprint when applicable,
sorted bounded reason codes, an injected creation timestamp, and its canonical
integrity fingerprint. `RecoveryEvent` carries the append-only event sequence, the
checkpoint fingerprint, the previous event fingerprint, the transition itself, the
idempotency key and request digest, bounded reason codes, the timestamp and its own
canonical integrity fingerprint. Both are frozen records serialized as canonical
JSON (sorted keys, tight separators, ASCII, no NaN).

## G3 evidence binding, and why executor success is not enough

Every persisted checkpoint binds to the project ID, task ID, execution/attempt ID,
the trusted canonical repository root, the G1 packet/policy/decision fingerprints,
the applicable G2 attempt fingerprint and the applicable G3 evidence fingerprint.

Those fingerprints are **recomputed from the immutable objects themselves** on
every append. A caller-supplied digest is never accepted in place of the object it
claims to describe. `TaskPacket` and `WorkspacePolicy` are revalidated,
`PermissionDecision.validate_binding` and
`EngineeringExecutionResult.validate_binding` are called explicitly, and a
`VerificationEvidence` record is revalidated and checked to bind to the same
project, task, execution, root and packet/policy/decision digests — and to the same
attempt digest when an attempt is supplied.

Only a valid G3 `VERIFIED` verdict can create a durable `VERIFIED` state, and each
of `FAILED`, `BLOCKED` and `INCONCLUSIVE` requires evidence whose verdict maps
exactly to it. `EVIDENCE_REQUIRED` is raised otherwise. This matters because an
executor's `SUCCESS` is a *claim about its own work*: G2 only establishes that a
process exited zero and its output parsed, never that the task was accomplished.
G3 is the only component that observes the workspace independently. So an
`EngineeringExecutionResult` with `status="SUCCESS"` and no evidence can reach
`EXECUTION_REPORTED` and nothing further; missing evidence after execution maps to
`REQUIRES_REVERIFICATION` or `INTERRUPTED`, never to `VERIFIED`.

Raw executor output, test output, prompts, environment values, credentials and
file contents are never serialized. Only identifiers, the trusted repository root,
SHA-256 digests, enumerated states and a fixed reason-code vocabulary reach the
database.

## Atomic transitions, idempotency and stale writers

`append` requires an `expected_checkpoint_fingerprint` compare-and-swap token:
`None` for an empty chain, otherwise the fingerprint of the latest checkpoint the
caller actually observed. A writer working from a superseded view is rejected with
`STALE_STATE`; nothing is merged and nothing is overwritten. Under contention,
`BEGIN IMMEDIATE` serializes writers, and a wait beyond the configured timeout
becomes a bounded `STORE_BUSY`.

Within one transaction the store reads the chain, validates it, checks the token
and the transition, writes the checkpoint row and the event row, then commits. Any
failure rolls the whole thing back, so the two records are always both present or
both absent. A reader on another connection sees the complete previous state while
that transaction is open; it never observes a checkpoint without its event.

`idempotency_key` is unique per `(project_id, execution_id)` and is stored
alongside a `request_digest` computed over the entire semantic request: target
state, compare-and-swap token, key, reason codes, identity, root and every
recomputed binding fingerprint. Repeating the identical request returns the stored
checkpoint and appends nothing. Reusing the key with different content raises
`IDEMPOTENCY_CONFLICT`. This is how the "commit succeeded but the response was
lost" case is resolved: by key lookup, never by appending a second record.

## Integrity chains and corruption behaviour

Checkpoints and events each form a hash chain: every record stores the previous
record's fingerprint, both in its canonical payload and in an indexed column, and
the event additionally stores the fingerprint of the checkpoint it accompanies.

Loading validates the chain completely and in order: payload field sets must match
exactly (an unknown or missing field blocks), states must be known enumeration
members, the recomputed fingerprint must equal the stored one, sequences must be
contiguous from 1, previous pointers must match in both payload and column,
identity and packet/policy/decision fingerprints must be constant across the
chain, every edge must be legal, and each event must agree with its checkpoint on
ID, state, reason codes, timestamp, idempotency key and request digest.

That detects a modified payload, a broken previous pointer in either chain, a
deleted middle record, a reordered record, and a spliced or duplicated record
wherever chain continuity can reveal it; an exact duplicate is additionally
refused by the unique fingerprint constraint.

On any of these, the store **blocks**: `latest_checkpoint` raises `CHAIN_CORRUPT`
and `assess` returns `BLOCK_CORRUPT_STATE` with `chain_valid=False`, no
reconstructed state and no last valid checkpoint. Nothing is repaired, nothing is
rewritten, and a corrupt record is never skipped in order to continue from a later
one. Repeated assessment is idempotent and leaves the stored bytes untouched.

Errors are sanitized into a fixed code set — `INVALID_CONFIGURATION`,
`UNTRUSTED_PATH`, `SCHEMA_UNSUPPORTED`, `SCHEMA_CORRUPT`, `BINDING_INVALID`,
`EVIDENCE_REQUIRED`, `ILLEGAL_TRANSITION`, `STALE_STATE`, `IDEMPOTENCY_CONFLICT`,
`DUPLICATE_RECORD`, `RECORD_LIMIT`, `CHAIN_CORRUPT`, `STORE_BUSY`, `STORE_CLOSED`,
`STORE_UNAVAILABLE` — and never carry a database path, SQL text, driver message,
credential, prompt, executor output or raw evidence.

## Why SHA-256 chains are not authentication

Every fingerprint is an unsigned SHA-256 integrity digest, and each record says so
in its `fingerprint_kind` field: `SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED`.

The chains detect accidental corruption, partial writes, truncation, reordering
and casual tampering. They do **not** detect a deliberate, competent rewrite. Any
local writer with write access to the database can edit a record, recompute its
digest, recompute every following digest, and produce a chain that validates
cleanly — this is demonstrated by a test, not merely asserted. There is no secret,
no key and no signature, so there is no replay protection and no proof of
authorship. Authenticated audit history, whether by MAC, signature or an external
append-only log, is deferred.

## Recovery decision table

`assess` reconstructs the latest trustworthy state and the safe next action. It is
read-only: it never writes, never re-executes, never reconnects to an external
session and never assumes an external process is still running. The mapping is
total and deterministic.

| Stored state | Reconstructed state | Action | G3 re-verification |
| --- | --- | --- | --- |
| (no records) | — | `RESUME_PLANNING` | no |
| `PLANNED` | `PLANNED` | `RESUME_PLANNING` | no |
| `EXECUTION_STARTED` | `INTERRUPTED` | `REVERIFY_WORKSPACE` | **yes** |
| `EXECUTION_REPORTED` | `REQUIRES_REVERIFICATION` | `REVERIFY_WORKSPACE` | **yes** |
| `VERIFICATION_STARTED` | `INTERRUPTED` | `REVERIFY_WORKSPACE` | **yes** |
| `VERIFIED` | `VERIFIED` | `NO_ACTION` | no |
| `FAILED` | `FAILED` | `REQUIRE_HUMAN_REVIEW` * | **yes** |
| `BLOCKED` | `BLOCKED` | `REQUIRE_HUMAN_REVIEW` * | **yes** |
| `INCONCLUSIVE` | `INCONCLUSIVE` | `REVERIFY_WORKSPACE` | **yes** |
| `INTERRUPTED` | `INTERRUPTED` | `REVERIFY_WORKSPACE` | **yes** |
| `REQUIRES_REVERIFICATION` | `REQUIRES_REVERIFICATION` | `REVERIFY_WORKSPACE` | **yes** |
| `ABANDONED` | `ABANDONED` | `NO_ACTION` | no |
| corrupt, unknown or incompatible | — | `BLOCK_CORRUPT_STATE` | **yes** |

\* becomes `RETRY_FROM_VERIFIED_CHECKPOINT`, with the reason code
`EARLIER_VERIFIED_CHECKPOINT`, when an earlier `VERIFIED` checkpoint exists in the
same chain.

Note the asymmetry that gives G4 its name: the *stored* state is durable history
and is never rewritten by an assessment, while the *reconstructed* state is what
ZERO may act on now. `EXECUTION_STARTED` with no later durable report reconstructs
as `INTERRUPTED`, not as progress. `VERIFIED` survives a restart only while its
entire chain and its referenced evidence binding validate; corrupt either and the
assessment blocks instead of downgrading quietly.

G4 never re-runs a task, never updates project milestones, never reattaches to a
Codex, Goose or Claude session and never marks anything complete.

## Crash coverage and its limits

`tests/g4_recovery/fixtures/recovery_writer.py` is a real writer driven against a
throwaway temporary database and terminated at three chosen points: before any
transaction, inside an uncommitted transaction after the checkpoint row is
inserted and before the event row is, and after a successful commit but before the
caller could use the returned checkpoint. After each kill the store is reopened.
The database always holds either the complete old state or the complete new state,
never half a checkpoint/event pair, and the "commit succeeded but the response was
lost" case resolves through idempotency-key lookup rather than a duplicate append.

**These are process-kill tests.** They demonstrate that abrupt process termination
cannot tear a transition. They do **not** demonstrate power-loss durability,
host-failure durability, or correctness on a filesystem or virtualisation layer
that reorders, caches or rolls back writes behind `fsync`. `synchronous = FULL`
asks the operating system to flush at commit; whether that flush truly reaches
stable media is a property of the hardware and filesystem, not of this module.

## What G4 is not

G4 is durable local process-state persistence and safe resume planning. It is not
a Git commit manager, a backup system, a distributed or replicated store, a
consensus system, authenticated evidence, protection against a hostile
administrator or anyone with write access to the database file, an external-agent
session continuation mechanism, an executor, a verifier, a reviewer or an
unattended queue.

There is no backup capability and no recovery from a deleted or corrupted database
file: corruption blocks, it does not restore. Retention is expressed only as a
floor; `RetentionPolicy` refuses to enable automatic deletion, and nothing in this
module removes durable history. Pruning, archiving and export remain the trusted
application's explicit responsibility.

## Deferred

* **G5 — independent reviewer workflow.** Recovery records a `VERIFIED` state
  bound to G3 evidence; it does not review the change, judge quality or approve
  merging. Review states and reviewer identity are not represented here.
* **G6 — controlled unattended execution.** Recovery produces a plan. Nothing in
  G4 dispatches, queues, schedules or retries work, and `RESUME_PLANNING` or
  `RETRY_FROM_VERIFIED_CHECKPOINT` are recommendations for a caller, not actions.
* **Authenticated HITL integration.** `REQUIRE_HUMAN_REVIEW` is a bounded reason
  code, not an approval record. Authenticated human approvals, and the
  authenticated audit history that would make the checkpoint chain tamper-evident
  against a privileged local writer, are later work.
