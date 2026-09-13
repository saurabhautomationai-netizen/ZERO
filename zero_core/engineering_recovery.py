"""G4 ZERO-owned durable recovery state and safe resume planning.

This module persists bounded lifecycle records and reconstructs a recovery
decision after interruption. It never executes engineering work, never runs a
subprocess, never verifies a workspace and never continues an external agent
session. It produces plans only; G3 remains the sole verification authority.

Fingerprints are unsigned SHA-256 integrity digests. They detect accidental or
partial corruption of a stored chain. They are not signatures, authentication or
replay protection: a local writer able to rewrite the whole database can
recompute every digest. Authenticated audit history is deferred.

Import is inert. No filesystem, environment, network or process access happens
until a store is explicitly opened.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Protocol
import hashlib
import json
import os
import re
import sqlite3
import stat

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, PermissionDecision, TaskPacket, WorkspacePolicy, _root,
)
from zero_core.engineering_execution import canonical_path
from zero_core.engineering_verification import VerificationEvidence, VerificationVerdict


SCHEMA_VERSION = 1
FINGERPRINT_KIND = "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"
MAX_REASON_CODES = 8

ERROR_CODES = frozenset({
    "INVALID_CONFIGURATION", "UNTRUSTED_PATH", "SCHEMA_UNSUPPORTED", "SCHEMA_CORRUPT",
    "BINDING_INVALID", "EVIDENCE_REQUIRED", "ILLEGAL_TRANSITION", "STALE_STATE",
    "IDEMPOTENCY_CONFLICT", "DUPLICATE_RECORD", "RECORD_LIMIT", "CHAIN_CORRUPT",
    "STORE_BUSY", "STORE_CLOSED", "STORE_UNAVAILABLE",
})

REASON_CODES = frozenset({
    "NO_DURABLE_RECORD", "PLANNING_RECORDED", "PLANNING_INCOMPLETE",
    "EXECUTION_DISPATCHED", "EXECUTION_INTERRUPTED", "EXECUTOR_CLAIM_RECORDED",
    "EXECUTOR_CLAIM_UNVERIFIED", "VERIFICATION_DISPATCHED", "VERIFICATION_INTERRUPTED",
    "VERIFIED_EVIDENCE_BOUND", "VERIFICATION_FAILED", "VERIFICATION_BLOCKED",
    "VERIFICATION_INCONCLUSIVE", "REVERIFICATION_REQUIRED", "EARLIER_VERIFIED_CHECKPOINT",
    "TERMINAL_ABANDONED", "CHAIN_CORRUPT", "OPERATOR_DECISION",
})


class RecoveryError(ValueError):
    """Fixed-code rejection. Never carries paths, SQL, evidence or output."""

    def __init__(self, code="INVALID_CONFIGURATION"):
        if code not in ERROR_CODES:
            code = "INVALID_CONFIGURATION"
        super().__init__(code)
        self.code = code


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise RecoveryError()
    return value


def _text(value, limit):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise RecoveryError()
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise RecoveryError()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise RecoveryError() from None
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RecoveryError()
    return value


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise RecoveryError()
    return value


def _count(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise RecoveryError()
    return value


def _reason_codes(values, default):
    if type(values) is not tuple:
        raise RecoveryError()
    codes = tuple(sorted(set(values))) or (default,)
    if len(codes) > MAX_REASON_CODES or any(code not in REASON_CODES for code in codes):
        raise RecoveryError()
    return codes


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
        return [_payload(item) for item in value]
    if type(value) in (str, int, bool) or value is None:
        return value
    raise RecoveryError()


class Record:
    """Canonical JSON only. No pickle, eval or unsafe deserialization anywhere."""

    def canonical_json(self):
        return json.dumps(_payload(self), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)

    def fingerprint(self):
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class RecoveryState(str, Enum):
    PLANNED = "PLANNED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_REPORTED = "EXECUTION_REPORTED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INTERRUPTED = "INTERRUPTED"
    REQUIRES_REVERIFICATION = "REQUIRES_REVERIFICATION"
    ABANDONED = "ABANDONED"


class RecoveryAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    RESUME_PLANNING = "RESUME_PLANNING"
    REVERIFY_WORKSPACE = "REVERIFY_WORKSPACE"
    RETRY_FROM_VERIFIED_CHECKPOINT = "RETRY_FROM_VERIFIED_CHECKPOINT"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"
    BLOCK_CORRUPT_STATE = "BLOCK_CORRUPT_STATE"


S = RecoveryState
A = RecoveryAction

# The only legal lifecycle edges. ``None`` is the empty chain, so every chain
# must begin at PLANNED. ABANDONED is terminal. VERIFIED is never overwritten in
# place: leaving it requires an explicit REQUIRES_REVERIFICATION or ABANDONED
# edge, and a fresh attempt uses a new execution ID and therefore a new chain.
LEGAL_TRANSITIONS = {
    None: frozenset({S.PLANNED}),
    S.PLANNED: frozenset({S.EXECUTION_STARTED, S.ABANDONED}),
    S.EXECUTION_STARTED: frozenset({S.EXECUTION_REPORTED, S.INTERRUPTED, S.ABANDONED}),
    S.EXECUTION_REPORTED: frozenset({S.VERIFICATION_STARTED, S.REQUIRES_REVERIFICATION,
                                     S.INTERRUPTED, S.ABANDONED}),
    S.VERIFICATION_STARTED: frozenset({S.VERIFIED, S.FAILED, S.BLOCKED, S.INCONCLUSIVE,
                                       S.INTERRUPTED, S.ABANDONED}),
    S.VERIFIED: frozenset({S.REQUIRES_REVERIFICATION, S.ABANDONED}),
    S.FAILED: frozenset({S.REQUIRES_REVERIFICATION, S.ABANDONED}),
    S.BLOCKED: frozenset({S.REQUIRES_REVERIFICATION, S.ABANDONED}),
    S.INCONCLUSIVE: frozenset({S.REQUIRES_REVERIFICATION, S.ABANDONED}),
    S.INTERRUPTED: frozenset({S.REQUIRES_REVERIFICATION, S.ABANDONED}),
    S.REQUIRES_REVERIFICATION: frozenset({S.VERIFICATION_STARTED, S.ABANDONED}),
    S.ABANDONED: frozenset(),
}

# Only a valid G3 evidence record can create one of these durable states, and its
# verdict must map exactly. An executor SUCCESS claim can never reach them.
VERDICT_STATES = {
    VerificationVerdict.VERIFIED: S.VERIFIED,
    VerificationVerdict.FAILED: S.FAILED,
    VerificationVerdict.BLOCKED: S.BLOCKED,
    VerificationVerdict.INCONCLUSIVE: S.INCONCLUSIVE,
}
EVIDENCE_REQUIRED_STATES = frozenset(VERDICT_STATES.values())
ATTEMPT_REQUIRED_STATES = EVIDENCE_REQUIRED_STATES | frozenset({S.EXECUTION_REPORTED, S.VERIFICATION_STARTED})
ATTEMPT_FORBIDDEN_STATES = frozenset({S.PLANNED, S.EXECUTION_STARTED})

DEFAULT_REASONS = {
    S.PLANNED: "PLANNING_RECORDED",
    S.EXECUTION_STARTED: "EXECUTION_DISPATCHED",
    S.EXECUTION_REPORTED: "EXECUTOR_CLAIM_RECORDED",
    S.VERIFICATION_STARTED: "VERIFICATION_DISPATCHED",
    S.VERIFIED: "VERIFIED_EVIDENCE_BOUND",
    S.FAILED: "VERIFICATION_FAILED",
    S.BLOCKED: "VERIFICATION_BLOCKED",
    S.INCONCLUSIVE: "VERIFICATION_INCONCLUSIVE",
    S.INTERRUPTED: "EXECUTION_INTERRUPTED",
    S.REQUIRES_REVERIFICATION: "REVERIFICATION_REQUIRED",
    S.ABANDONED: "TERMINAL_ABANDONED",
}

# Deterministic crash-recovery decision table. The durable stored state is never
# rewritten by an assessment; the reconstructed state is what ZERO may trust now.
RECOVERY_DECISIONS = {
    None: (None, A.RESUME_PLANNING, False, "NO_DURABLE_RECORD"),
    S.PLANNED: (S.PLANNED, A.RESUME_PLANNING, False, "PLANNING_INCOMPLETE"),
    S.EXECUTION_STARTED: (S.INTERRUPTED, A.REVERIFY_WORKSPACE, True, "EXECUTION_INTERRUPTED"),
    S.EXECUTION_REPORTED: (S.REQUIRES_REVERIFICATION, A.REVERIFY_WORKSPACE, True, "EXECUTOR_CLAIM_UNVERIFIED"),
    S.VERIFICATION_STARTED: (S.INTERRUPTED, A.REVERIFY_WORKSPACE, True, "VERIFICATION_INTERRUPTED"),
    S.VERIFIED: (S.VERIFIED, A.NO_ACTION, False, "VERIFIED_EVIDENCE_BOUND"),
    S.FAILED: (S.FAILED, A.REQUIRE_HUMAN_REVIEW, True, "VERIFICATION_FAILED"),
    S.BLOCKED: (S.BLOCKED, A.REQUIRE_HUMAN_REVIEW, True, "VERIFICATION_BLOCKED"),
    S.INCONCLUSIVE: (S.INCONCLUSIVE, A.REVERIFY_WORKSPACE, True, "VERIFICATION_INCONCLUSIVE"),
    S.INTERRUPTED: (S.INTERRUPTED, A.REVERIFY_WORKSPACE, True, "EXECUTION_INTERRUPTED"),
    S.REQUIRES_REVERIFICATION: (S.REQUIRES_REVERIFICATION, A.REVERIFY_WORKSPACE, True, "REVERIFICATION_REQUIRED"),
    S.ABANDONED: (S.ABANDONED, A.NO_ACTION, False, "TERMINAL_ABANDONED"),
}


class DurabilityMode(str, Enum):
    """The only durability contract G4 implements and therefore permits.

    Rollback-journal mode keeps the durable state in one file plus a transient
    journal, so a killed process leaves either the complete old state or the
    complete new state. WAL is rejected: it adds -wal/-shm sidecars, needs shared
    memory that some filesystems do not provide, and moves commit durability into
    a checkpoint this module does not control.
    """

    FULL_SYNCHRONOUS_DELETE_JOURNAL = "FULL_SYNCHRONOUS_DELETE_JOURNAL"


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention is expressed as a floor, never as automatic destructive deletion."""

    minimum_retained_checkpoints: int = 0
    minimum_retained_events: int = 0
    automatic_deletion_enabled: bool = False

    def __post_init__(self):
        _count(self.minimum_retained_checkpoints, 0, 1000000)
        _count(self.minimum_retained_events, 0, 1000000)
        if type(self.automatic_deletion_enabled) is not bool or self.automatic_deletion_enabled:
            raise RecoveryError()

    def fingerprint(self):
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TrustedRecoveryConfiguration:
    """Immutable trusted application input. The only source of the store location.

    No TaskPacket, executor output, prompt or external agent can reach these
    fields: the store API accepts no path, no filename and no schema version.
    """

    project_id: str
    repository_root: str
    recovery_directory: str
    database_path: str
    schema_version: int = SCHEMA_VERSION
    max_record_bytes: int = 16384
    durability: DurabilityMode = DurabilityMode.FULL_SYNCHRONOUS_DELETE_JOURNAL
    busy_timeout_ms: int = 5000
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)

    def __post_init__(self):
        if os.name not in ("nt", "posix"):
            raise RecoveryError()
        _id(self.project_id)
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise RecoveryError("SCHEMA_UNSUPPORTED")
        if type(self.durability) is not DurabilityMode:
            raise RecoveryError()
        _count(self.max_record_bytes, 256, 1048576)
        _count(self.busy_timeout_ms, 100, 60000)
        if type(self.retention) is not RetentionPolicy:
            raise RecoveryError()
        self.retention.__post_init__()
        try:
            root = canonical_path(self.repository_root, directory=True)
            directory = canonical_path(self.recovery_directory, directory=True)
        except (ValueError, OSError):
            raise RecoveryError("UNTRUSTED_PATH") from None
        _text(root, 1024)
        _text(directory, 1024)
        _root(root)
        object.__setattr__(self, "repository_root", root)
        object.__setattr__(self, "recovery_directory", directory)
        object.__setattr__(self, "database_path", self._database(directory))

    def _database(self, directory):
        value = _text(self.database_path, 1024)
        path = Path(value)
        if not path.is_absolute() or value.startswith(("//", "\\\\")):
            raise RecoveryError("UNTRUSTED_PATH")
        name = path.name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name) or name.endswith("."):
            raise RecoveryError("UNTRUSTED_PATH")
        try:
            parent = canonical_path(path.parent.as_posix(), directory=True)
        except (ValueError, OSError):
            raise RecoveryError("UNTRUSTED_PATH") from None
        prefix = directory if directory.endswith("/") else directory + "/"
        if parent != directory and not parent.startswith(prefix):
            raise RecoveryError("UNTRUSTED_PATH")
        resolved = parent + name if parent.endswith("/") else parent + "/" + name
        try:
            info = Path(resolved).lstat()
        except FileNotFoundError:
            return resolved
        except OSError:
            raise RecoveryError("UNTRUSTED_PATH") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RecoveryError("UNTRUSTED_PATH")
        if not stat.S_ISREG(info.st_mode):
            raise RecoveryError("UNTRUSTED_PATH")
        return resolved

    def fingerprint(self):
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["durability"] = self.durability.value
        data["retention"] = self.retention.fingerprint()
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True).encode("utf-8")).hexdigest()


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdentifierSource(Protocol):
    def next_id(self) -> str: ...


@dataclass(frozen=True)
class RecoveryCheckpoint(Record):
    schema_version: int
    checkpoint_id: str
    project_id: str
    task_id: str
    execution_id: str
    repository_root: str
    sequence: int
    previous_checkpoint_fingerprint: str | None
    state: RecoveryState
    packet_fingerprint: str
    policy_fingerprint: str
    decision_fingerprint: str
    attempt_fingerprint: str | None
    evidence_fingerprint: str | None
    reason_codes: tuple[str, ...]
    created_at: datetime
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise RecoveryError("SCHEMA_UNSUPPORTED")
        if self.fingerprint_kind != FINGERPRINT_KIND:
            raise RecoveryError()
        for value in (self.checkpoint_id, self.project_id, self.task_id, self.execution_id):
            _id(value)
        _text(self.repository_root, 1024)
        try:
            _root(self.repository_root)
        except (ValueError, TypeError):
            raise RecoveryError("UNTRUSTED_PATH") from None
        _count(self.sequence, 1, 1000000)
        if type(self.state) is not RecoveryState:
            raise RecoveryError()
        for value in (self.packet_fingerprint, self.policy_fingerprint, self.decision_fingerprint):
            _digest(value)
        for value in (self.previous_checkpoint_fingerprint, self.attempt_fingerprint, self.evidence_fingerprint):
            if value is not None:
                _digest(value)
        if (self.sequence == 1) != (self.previous_checkpoint_fingerprint is None):
            raise RecoveryError()
        if self.state in EVIDENCE_REQUIRED_STATES and self.evidence_fingerprint is None:
            raise RecoveryError("EVIDENCE_REQUIRED")
        if self.state in ATTEMPT_FORBIDDEN_STATES and (self.attempt_fingerprint or self.evidence_fingerprint):
            raise RecoveryError()
        if self.state in ATTEMPT_REQUIRED_STATES and self.attempt_fingerprint is None:
            raise RecoveryError()
        object.__setattr__(self, "reason_codes", _reason_codes(self.reason_codes, DEFAULT_REASONS[self.state]))
        _time(self.created_at)


@dataclass(frozen=True)
class RecoveryEvent(Record):
    schema_version: int
    event_id: str
    project_id: str
    task_id: str
    execution_id: str
    sequence: int
    checkpoint_fingerprint: str
    previous_event_fingerprint: str | None
    from_state: RecoveryState | None
    to_state: RecoveryState
    idempotency_key: str
    request_digest: str
    reason_codes: tuple[str, ...]
    created_at: datetime
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise RecoveryError("SCHEMA_UNSUPPORTED")
        if self.fingerprint_kind != FINGERPRINT_KIND:
            raise RecoveryError()
        for value in (self.event_id, self.project_id, self.task_id, self.execution_id, self.idempotency_key):
            _id(value)
        _count(self.sequence, 1, 1000000)
        _digest(self.checkpoint_fingerprint)
        _digest(self.request_digest)
        if self.previous_event_fingerprint is not None:
            _digest(self.previous_event_fingerprint)
        if (self.sequence == 1) != (self.previous_event_fingerprint is None):
            raise RecoveryError()
        if self.from_state is not None and type(self.from_state) is not RecoveryState:
            raise RecoveryError()
        if type(self.to_state) is not RecoveryState:
            raise RecoveryError()
        if self.to_state not in LEGAL_TRANSITIONS.get(self.from_state, frozenset()):
            raise RecoveryError("ILLEGAL_TRANSITION")
        object.__setattr__(self, "reason_codes", _reason_codes(self.reason_codes, DEFAULT_REASONS[self.to_state]))
        _time(self.created_at)


@dataclass(frozen=True)
class RecoveryAssessment(Record):
    schema_version: int
    project_id: str
    task_id: str
    execution_id: str
    state: RecoveryState | None
    chain_valid: bool
    action: RecoveryAction
    reason_codes: tuple[str, ...]
    last_valid_checkpoint: RecoveryCheckpoint | None
    reverification_required: bool
    assessed_at: datetime
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise RecoveryError("SCHEMA_UNSUPPORTED")
        if self.fingerprint_kind != FINGERPRINT_KIND:
            raise RecoveryError()
        for value in (self.project_id, self.task_id, self.execution_id):
            _id(value)
        if self.state is not None and type(self.state) is not RecoveryState:
            raise RecoveryError()
        if type(self.action) is not RecoveryAction:
            raise RecoveryError()
        for value in (self.chain_valid, self.reverification_required):
            if type(value) is not bool:
                raise RecoveryError()
        if self.last_valid_checkpoint is not None:
            if type(self.last_valid_checkpoint) is not RecoveryCheckpoint:
                raise RecoveryError()
            self.last_valid_checkpoint.__post_init__()
        if not self.chain_valid and (self.action is not A.BLOCK_CORRUPT_STATE
                                     or self.last_valid_checkpoint is not None or self.state is not None):
            raise RecoveryError("CHAIN_CORRUPT")
        object.__setattr__(self, "reason_codes", _reason_codes(self.reason_codes, "NO_DURABLE_RECORD"))
        _time(self.assessed_at)


TABLES = ("recovery_checkpoint", "recovery_event", "recovery_schema")

SCHEMA_COLUMNS = {
    "recovery_schema": ("id", "schema_version", "durability_mode", "created_at"),
    "recovery_checkpoint": ("checkpoint_id", "project_id", "task_id", "execution_id", "sequence",
                            "payload", "fingerprint", "previous_fingerprint", "request_digest",
                            "idempotency_key"),
    "recovery_event": ("event_id", "project_id", "task_id", "execution_id", "sequence",
                       "checkpoint_id", "payload", "fingerprint", "previous_fingerprint"),
}

# Every statement below is a module constant. No caller value, table name or
# column name is ever interpolated into SQL; all values are bound parameters.
CREATE_SCHEMA_TABLE = (
    "CREATE TABLE recovery_schema ("
    " id INTEGER PRIMARY KEY CHECK (id = 1),"
    " schema_version INTEGER NOT NULL,"
    " durability_mode TEXT NOT NULL,"
    " created_at TEXT NOT NULL)")
CREATE_CHECKPOINT_TABLE = (
    "CREATE TABLE recovery_checkpoint ("
    " checkpoint_id TEXT PRIMARY KEY NOT NULL,"
    " project_id TEXT NOT NULL,"
    " task_id TEXT NOT NULL,"
    " execution_id TEXT NOT NULL,"
    " sequence INTEGER NOT NULL,"
    " payload TEXT NOT NULL,"
    " fingerprint TEXT NOT NULL UNIQUE,"
    " previous_fingerprint TEXT,"
    " request_digest TEXT NOT NULL,"
    " idempotency_key TEXT NOT NULL,"
    " UNIQUE (project_id, execution_id, sequence),"
    " UNIQUE (project_id, execution_id, idempotency_key))")
CREATE_EVENT_TABLE = (
    "CREATE TABLE recovery_event ("
    " event_id TEXT PRIMARY KEY NOT NULL,"
    " project_id TEXT NOT NULL,"
    " task_id TEXT NOT NULL,"
    " execution_id TEXT NOT NULL,"
    " sequence INTEGER NOT NULL,"
    " checkpoint_id TEXT NOT NULL REFERENCES recovery_checkpoint (checkpoint_id),"
    " payload TEXT NOT NULL,"
    " fingerprint TEXT NOT NULL UNIQUE,"
    " previous_fingerprint TEXT,"
    " UNIQUE (project_id, execution_id, sequence))")
INSERT_SCHEMA =("INSERT INTO recovery_schema (id, schema_version, durability_mode, created_at)"
                 " VALUES (1, ?, ?, ?)")
SELECT_SCHEMA = "SELECT id, schema_version, durability_mode FROM recovery_schema"
SELECT_TABLES = "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
SELECT_CHECKPOINTS = ("SELECT sequence, payload, fingerprint, previous_fingerprint, request_digest,"
                      " idempotency_key, checkpoint_id, task_id FROM recovery_checkpoint"
                      " WHERE project_id = ? AND execution_id = ? ORDER BY sequence ASC")
SELECT_EVENTS = ("SELECT sequence, payload, fingerprint, previous_fingerprint, checkpoint_id, event_id"
                 " FROM recovery_event WHERE project_id = ? AND execution_id = ? ORDER BY sequence ASC")
SELECT_IDEMPOTENT = ("SELECT payload, fingerprint, request_digest FROM recovery_checkpoint"
                     " WHERE project_id = ? AND execution_id = ? AND idempotency_key = ?")
INSERT_CHECKPOINT = ("INSERT INTO recovery_checkpoint (checkpoint_id, project_id, task_id, execution_id,"
                     " sequence, payload, fingerprint, previous_fingerprint, request_digest, idempotency_key)"
                     " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
INSERT_EVENT = ("INSERT INTO recovery_event (event_id, project_id, task_id, execution_id, sequence,"
                " checkpoint_id, payload, fingerprint, previous_fingerprint)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"
BEGIN_DEFERRED = "BEGIN DEFERRED"
COMMIT = "COMMIT"
ROLLBACK = "ROLLBACK"
PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys = ON"
PRAGMA_JOURNAL = "PRAGMA journal_mode = DELETE"
PRAGMA_SYNCHRONOUS = "PRAGMA synchronous = FULL"
READ_FOREIGN_KEYS = "PRAGMA foreign_keys"
READ_JOURNAL = "PRAGMA journal_mode"
READ_SYNCHRONOUS = "PRAGMA synchronous"
READ_BUSY_TIMEOUT = "PRAGMA busy_timeout"
READ_TABLE_INFO = ("SELECT name FROM pragma_table_info(?) ORDER BY cid")


def _sqlite_error(error):
    """Map a driver failure onto a bounded code without leaking its message."""
    text = str(error).lower()
    code = getattr(error, "sqlite_errorcode", None)
    if code in (5, 6, 261, 262, 517) or "locked" in text or "busy" in text:
        return RecoveryError("STORE_BUSY")
    if isinstance(error, sqlite3.IntegrityError):
        return RecoveryError("DUPLICATE_RECORD")
    return RecoveryError("STORE_UNAVAILABLE")


def _decode(cls, payload, expected_fingerprint):
    """Strict canonical decode. Unknown fields, states or digests fail closed."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        raise RecoveryError("CHAIN_CORRUPT") from None
    if type(data) is not dict or set(data) != {f.name for f in fields(cls)}:
        raise RecoveryError("CHAIN_CORRUPT")
    try:
        for name in ("state", "from_state", "to_state"):
            if name in data and data[name] is not None:
                data[name] = RecoveryState(data[name])
        for name in ("created_at",):
            data[name] = datetime.fromisoformat(data[name])
        if type(data["reason_codes"]) is not list:
            raise ValueError()
        data["reason_codes"] = tuple(data["reason_codes"])
        record = cls(**data)
    except (ValueError, TypeError, KeyError, RecoveryError):
        raise RecoveryError("CHAIN_CORRUPT") from None
    if record.fingerprint() != expected_fingerprint:
        raise RecoveryError("CHAIN_CORRUPT")
    return record


class RecoveryStore:
    """Durable local recovery state. Opening is the only filesystem action.

    The store performs no execution, no verification and no network access. It
    holds one SQLite connection, closed deterministically by ``close``.
    """

    def __init__(self, configuration, *, clock, id_source):
        if type(configuration) is not TrustedRecoveryConfiguration:
            raise RecoveryError()
        configuration.__post_init__()
        for service in (clock, id_source):
            if service is None:
                raise RecoveryError()
        if not callable(getattr(clock, "now", None)) or not callable(getattr(id_source, "next_id", None)):
            raise RecoveryError()
        self._config = configuration
        self._clock = clock
        self._ids = id_source
        self._connection = None
        self._connection = self._connect()
        try:
            self._prepare_schema()
        except BaseException:
            self.close()
            raise

    # -- lifecycle ---------------------------------------------------------

    def _connect(self):
        config = self._config
        try:
            connection = sqlite3.connect(
                config.database_path, timeout=config.busy_timeout_ms / 1000.0,
                isolation_level=None, check_same_thread=True, uri=False,
            )
        except sqlite3.Error as error:
            raise _sqlite_error(error) from None
        try:
            connection.execute(PRAGMA_FOREIGN_KEYS)
            connection.execute(PRAGMA_JOURNAL)
            connection.execute(PRAGMA_SYNCHRONOUS)
            journal = str(connection.execute(READ_JOURNAL).fetchone()[0]).lower()
            synchronous = int(connection.execute(READ_SYNCHRONOUS).fetchone()[0])
            foreign_keys = int(connection.execute(READ_FOREIGN_KEYS).fetchone()[0])
            timeout = int(connection.execute(READ_BUSY_TIMEOUT).fetchone()[0])
        except sqlite3.Error as error:
            connection.close()
            raise _sqlite_error(error) from None
        if journal != "delete" or synchronous != 2 or foreign_keys != 1 or timeout <= 0:
            connection.close()
            raise RecoveryError("STORE_UNAVAILABLE")
        return connection

    def _prepare_schema(self):
        connection = self._connection
        created = self._clock.now()
        _time(created)
        try:
            connection.execute(BEGIN_IMMEDIATE)
        except sqlite3.Error as error:
            raise _sqlite_error(error) from None
        try:
            names = {row[0] for row in connection.execute(SELECT_TABLES)}
            if not names:
                # One transaction creates every table and the schema row, so an
                # interrupted first open rolls back to an empty file that the
                # next open can initialise cleanly.
                connection.execute(CREATE_SCHEMA_TABLE)
                connection.execute(CREATE_CHECKPOINT_TABLE)
                connection.execute(CREATE_EVENT_TABLE)
                connection.execute(INSERT_SCHEMA, (SCHEMA_VERSION, self._config.durability.value,
                                                   created.isoformat()))
            elif names != set(TABLES):
                raise RecoveryError("SCHEMA_CORRUPT")
            self._validate_schema(connection)
            connection.execute(COMMIT)
        except BaseException as error:
            self._rollback(connection)
            if isinstance(error, sqlite3.Error):
                raise _sqlite_error(error) from None
            raise

    def _validate_schema(self, connection):
        for table in TABLES:
            columns = tuple(row[0] for row in connection.execute(READ_TABLE_INFO, (table,)))
            if columns != SCHEMA_COLUMNS[table]:
                raise RecoveryError("SCHEMA_CORRUPT")
        rows = connection.execute(SELECT_SCHEMA).fetchall()
        if len(rows) != 1 or rows[0][0] != 1:
            raise RecoveryError("SCHEMA_CORRUPT")
        version, durability = rows[0][1], rows[0][2]
        if type(version) is not int or version != SCHEMA_VERSION:
            # A newer or unknown schema is never migrated, adapted or truncated.
            raise RecoveryError("SCHEMA_UNSUPPORTED")
        if durability != self._config.durability.value:
            raise RecoveryError("SCHEMA_CORRUPT")

    @staticmethod
    def _rollback(connection):
        try:
            connection.execute(ROLLBACK)
        except sqlite3.Error:
            pass

    def close(self):
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
        return False

    def _require_open(self):
        if self._connection is None:
            raise RecoveryError("STORE_CLOSED")
        return self._connection

    # -- binding -----------------------------------------------------------

    def _bindings(self, *, task_id, execution_id, to_state, packet, policy, decision, attempt, evidence):
        """Recompute every fingerprint from the immutable objects themselves.

        A caller-supplied digest is never accepted in place of the object it
        claims to describe, and executor claims never establish verification.
        """
        config = self._config
        try:
            packet = TaskPacket.model_validate(packet)
            policy = WorkspacePolicy.model_validate(policy)
            if type(decision) is not PermissionDecision:
                raise ValueError()
            decision.validate_binding(packet, policy)
            if (packet.project_id, packet.repository_root) != (config.project_id, config.repository_root):
                raise ValueError()
            if (policy.project_id, policy.repository_root) != (config.project_id, config.repository_root):
                raise ValueError()
            if packet.task_id != task_id:
                raise ValueError()
        except (ValueError, TypeError, OSError, AttributeError):
            raise RecoveryError("BINDING_INVALID") from None

        attempt_fingerprint = None
        if attempt is not None:
            try:
                if type(attempt) is not EngineeringExecutionResult:
                    raise ValueError()
                attempt.validate_binding(packet, decision, policy)
                if (attempt.project_id, attempt.task_id, attempt.execution_id) != (
                        config.project_id, task_id, execution_id):
                    raise ValueError()
            except (ValueError, TypeError, OSError, AttributeError):
                raise RecoveryError("BINDING_INVALID") from None
            attempt_fingerprint = attempt.fingerprint()

        evidence_fingerprint = None
        if evidence is not None:
            try:
                if type(evidence) is not VerificationEvidence:
                    raise ValueError()
                evidence.__post_init__()
                binding = evidence.binding
                binding.__post_init__()
                if (binding.project_id, binding.task_id, binding.execution_id, binding.repository_root) != (
                        config.project_id, task_id, execution_id, config.repository_root):
                    raise ValueError()
                if (binding.packet_digest, binding.policy_digest, binding.decision_digest) != (
                        packet.fingerprint(), policy.fingerprint(), decision.fingerprint()):
                    raise ValueError()
                if attempt is not None and evidence.execution_digest != attempt_fingerprint:
                    raise ValueError()
            except (ValueError, TypeError, OSError, AttributeError):
                raise RecoveryError("BINDING_INVALID") from None
            evidence_fingerprint = evidence.fingerprint()

        self._authority(to_state, attempt, evidence)
        return {
            "packet_fingerprint": packet.fingerprint(),
            "policy_fingerprint": policy.fingerprint(),
            "decision_fingerprint": decision.fingerprint(),
            "attempt_fingerprint": attempt_fingerprint,
            "evidence_fingerprint": evidence_fingerprint,
        }

    @staticmethod
    def _authority(to_state, attempt, evidence):
        """Only a valid G3 verdict can create a durable verification outcome."""
        if to_state in ATTEMPT_FORBIDDEN_STATES and (attempt is not None or evidence is not None):
            raise RecoveryError("BINDING_INVALID")
        if to_state in ATTEMPT_REQUIRED_STATES and attempt is None:
            raise RecoveryError("BINDING_INVALID")
        if to_state in EVIDENCE_REQUIRED_STATES:
            if evidence is None:
                raise RecoveryError("EVIDENCE_REQUIRED")
            if VERDICT_STATES.get(evidence.verdict) is not to_state:
                raise RecoveryError("EVIDENCE_REQUIRED")
        elif evidence is not None:
            raise RecoveryError("BINDING_INVALID")

    def _request_digest(self, *, task_id, execution_id, to_state, expected, idempotency_key,
                        reason_codes, bindings):
        data = dict(bindings)
        data.update({
            "project_id": self._config.project_id, "task_id": task_id, "execution_id": execution_id,
            "repository_root": self._config.repository_root, "to_state": to_state.value,
            "expected_checkpoint_fingerprint": expected, "idempotency_key": idempotency_key,
            "reason_codes": list(reason_codes), "schema_version": SCHEMA_VERSION,
        })
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()

    # -- append ------------------------------------------------------------

    def append(self, *, task_id, execution_id, to_state, expected_checkpoint_fingerprint,
               idempotency_key, packet, policy, decision, attempt=None, evidence=None,
               reason_codes=()):
        """Atomically append one checkpoint and its event, or write nothing.

        ``expected_checkpoint_fingerprint`` is a compare-and-swap token: ``None``
        for an empty chain, otherwise the fingerprint of the latest checkpoint the
        caller observed. A stale writer is rejected, never merged.
        """
        connection = self._require_open()
        config = self._config
        if type(to_state) is not RecoveryState:
            raise RecoveryError("ILLEGAL_TRANSITION")
        _id(task_id)
        _id(execution_id)
        _id(idempotency_key)
        if expected_checkpoint_fingerprint is not None:
            _digest(expected_checkpoint_fingerprint)
        codes = _reason_codes(reason_codes, DEFAULT_REASONS[to_state])
        bindings = self._bindings(task_id=task_id, execution_id=execution_id, to_state=to_state,
                                  packet=packet, policy=policy, decision=decision,
                                  attempt=attempt, evidence=evidence)
        request_digest = self._request_digest(
            task_id=task_id, execution_id=execution_id, to_state=to_state,
            expected=expected_checkpoint_fingerprint, idempotency_key=idempotency_key,
            reason_codes=codes, bindings=bindings)

        try:
            connection.execute(BEGIN_IMMEDIATE)
        except sqlite3.Error as error:
            raise _sqlite_error(error) from None
        try:
            key = (config.project_id, execution_id)
            existing = connection.execute(SELECT_IDEMPOTENT, key + (idempotency_key,)).fetchone()
            if existing is not None:
                # The commit already happened; the response was lost. Return the
                # stored record instead of appending a second one.
                if existing[2] != request_digest:
                    raise RecoveryError("IDEMPOTENCY_CONFLICT")
                stored = _decode(RecoveryCheckpoint, existing[0], existing[1])
                connection.execute(COMMIT)
                return stored

            checkpoints, events = self._chain(connection, task_id, execution_id)
            latest = checkpoints[-1] if checkpoints else None
            previous_event = events[-1] if events else None
            if (latest.fingerprint() if latest is not None else None) != expected_checkpoint_fingerprint:
                raise RecoveryError("STALE_STATE")
            from_state = latest.state if latest is not None else None
            if to_state not in LEGAL_TRANSITIONS.get(from_state, frozenset()):
                raise RecoveryError("ILLEGAL_TRANSITION")
            if latest is not None:
                if (latest.project_id, latest.task_id, latest.execution_id, latest.repository_root) != (
                        config.project_id, task_id, execution_id, config.repository_root):
                    raise RecoveryError("BINDING_INVALID")
                for name in ("packet_fingerprint", "policy_fingerprint", "decision_fingerprint"):
                    if getattr(latest, name) != bindings[name]:
                        raise RecoveryError("BINDING_INVALID")
                if latest.attempt_fingerprint is not None and bindings["attempt_fingerprint"] not in (
                        None, latest.attempt_fingerprint):
                    raise RecoveryError("BINDING_INVALID")
                if bindings["attempt_fingerprint"] is None and latest.attempt_fingerprint is not None:
                    bindings["attempt_fingerprint"] = latest.attempt_fingerprint

            now = self._clock.now()
            _time(now)
            sequence = (latest.sequence + 1) if latest is not None else 1
            checkpoint = RecoveryCheckpoint(
                schema_version=SCHEMA_VERSION, checkpoint_id=_id(self._ids.next_id()),
                project_id=config.project_id, task_id=task_id, execution_id=execution_id,
                repository_root=config.repository_root, sequence=sequence,
                previous_checkpoint_fingerprint=(latest.fingerprint() if latest is not None else None),
                state=to_state, reason_codes=codes, created_at=now, **bindings)
            checkpoint_payload = checkpoint.canonical_json()
            checkpoint_fingerprint = checkpoint.fingerprint()
            event = RecoveryEvent(
                schema_version=SCHEMA_VERSION, event_id=_id(self._ids.next_id()),
                project_id=config.project_id, task_id=task_id, execution_id=execution_id,
                sequence=sequence, checkpoint_fingerprint=checkpoint_fingerprint,
                previous_event_fingerprint=(previous_event.fingerprint() if previous_event is not None else None),
                from_state=from_state, to_state=to_state, idempotency_key=idempotency_key,
                request_digest=request_digest, reason_codes=codes, created_at=now)
            event_payload = event.canonical_json()
            for payload in (checkpoint_payload, event_payload):
                if len(payload.encode("utf-8")) > config.max_record_bytes:
                    raise RecoveryError("RECORD_LIMIT")

            connection.execute(INSERT_CHECKPOINT, (
                checkpoint.checkpoint_id, config.project_id, task_id, execution_id, sequence,
                checkpoint_payload, checkpoint_fingerprint, checkpoint.previous_checkpoint_fingerprint,
                request_digest, idempotency_key))
            connection.execute(INSERT_EVENT, (
                event.event_id, config.project_id, task_id, execution_id, sequence,
                checkpoint.checkpoint_id, event_payload, event.fingerprint(),
                event.previous_event_fingerprint))
            connection.execute(COMMIT)
            return checkpoint
        except BaseException as error:
            self._rollback(connection)
            if isinstance(error, sqlite3.Error):
                raise _sqlite_error(error) from None
            raise

    # -- read and recover --------------------------------------------------

    def _chain(self, connection, task_id, execution_id):
        """Validate the complete stored chain or fail. Never skip a bad record."""
        config = self._config
        key = (config.project_id, execution_id)
        checkpoint_rows = connection.execute(SELECT_CHECKPOINTS, key).fetchall()
        event_rows = connection.execute(SELECT_EVENTS, key).fetchall()
        if len(checkpoint_rows) != len(event_rows):
            raise RecoveryError("CHAIN_CORRUPT")
        checkpoints = []
        events = []
        previous_checkpoint = None
        previous_event = None
        for index, row in enumerate(checkpoint_rows):
            sequence, payload, stored, previous, request_digest, idempotency_key, checkpoint_id, row_task = row
            checkpoint = _decode(RecoveryCheckpoint, payload, stored)
            expected_previous = previous_checkpoint.fingerprint() if previous_checkpoint is not None else None
            if sequence != index + 1 or checkpoint.sequence != sequence:
                raise RecoveryError("CHAIN_CORRUPT")
            if checkpoint.previous_checkpoint_fingerprint != expected_previous or previous != expected_previous:
                raise RecoveryError("CHAIN_CORRUPT")
            if (checkpoint.checkpoint_id, checkpoint.task_id) != (checkpoint_id, row_task):
                raise RecoveryError("CHAIN_CORRUPT")
            if (checkpoint.project_id, checkpoint.execution_id) != key:
                raise RecoveryError("CHAIN_CORRUPT")
            if checkpoint.repository_root != config.repository_root:
                raise RecoveryError("BINDING_INVALID")
            if previous_checkpoint is not None and (
                    checkpoint.task_id != previous_checkpoint.task_id
                    or checkpoint.packet_fingerprint != previous_checkpoint.packet_fingerprint
                    or checkpoint.policy_fingerprint != previous_checkpoint.policy_fingerprint
                    or checkpoint.decision_fingerprint != previous_checkpoint.decision_fingerprint):
                raise RecoveryError("CHAIN_CORRUPT")
            from_state = previous_checkpoint.state if previous_checkpoint is not None else None
            if checkpoint.state not in LEGAL_TRANSITIONS.get(from_state, frozenset()):
                raise RecoveryError("CHAIN_CORRUPT")

            event_sequence, event_payload, event_stored, event_previous, event_checkpoint, event_id = event_rows[index]
            event = _decode(RecoveryEvent, event_payload, event_stored)
            expected_event_previous = previous_event.fingerprint() if previous_event is not None else None
            if event_sequence != index + 1 or event.sequence != event_sequence:
                raise RecoveryError("CHAIN_CORRUPT")
            if event.previous_event_fingerprint != expected_event_previous or event_previous != expected_event_previous:
                raise RecoveryError("CHAIN_CORRUPT")
            if event.checkpoint_fingerprint != checkpoint.fingerprint() or event_checkpoint != checkpoint.checkpoint_id:
                raise RecoveryError("CHAIN_CORRUPT")
            if event.event_id != event_id or (event.project_id, event.execution_id) != key:
                raise RecoveryError("CHAIN_CORRUPT")
            if event.task_id != checkpoint.task_id or event.to_state != checkpoint.state or event.from_state != from_state:
                raise RecoveryError("CHAIN_CORRUPT")
            if (event.idempotency_key, event.request_digest) != (idempotency_key, request_digest):
                raise RecoveryError("CHAIN_CORRUPT")
            if event.reason_codes != checkpoint.reason_codes or event.created_at != checkpoint.created_at:
                raise RecoveryError("CHAIN_CORRUPT")

            checkpoints.append(checkpoint)
            events.append(event)
            previous_checkpoint = checkpoint
            previous_event = event
        if checkpoints and task_id is not None and checkpoints[-1].task_id != task_id:
            raise RecoveryError("BINDING_INVALID")
        return tuple(checkpoints), tuple(events)

    def latest_checkpoint(self, *, task_id, execution_id):
        """Validated latest checkpoint, or None for an empty chain."""
        connection = self._require_open()
        _id(task_id)
        _id(execution_id)
        try:
            connection.execute(BEGIN_DEFERRED)
        except sqlite3.Error as error:
            raise _sqlite_error(error) from None
        try:
            checkpoints, _events = self._chain(connection, task_id, execution_id)
            connection.execute(COMMIT)
            return checkpoints[-1] if checkpoints else None
        except BaseException as error:
            self._rollback(connection)
            if isinstance(error, sqlite3.Error):
                raise _sqlite_error(error) from None
            raise

    def assess(self, *, task_id, execution_id):
        """Reconstruct the latest trustworthy state and the safe next action.

        This never writes, never assumes an interrupted process completed, never
        assumes an external process is still running and never reconnects to any
        external agent session. Corruption blocks; it is never repaired.
        """
        connection = self._require_open()
        _id(task_id)
        _id(execution_id)
        assessed_at = self._clock.now()
        _time(assessed_at)
        common = dict(schema_version=SCHEMA_VERSION, project_id=self._config.project_id,
                      task_id=task_id, execution_id=execution_id, assessed_at=assessed_at)
        try:
            connection.execute(BEGIN_DEFERRED)
        except sqlite3.Error as error:
            raise _sqlite_error(error) from None
        try:
            history, _events = self._chain(connection, task_id, execution_id)
            connection.execute(COMMIT)
        except BaseException as error:
            self._rollback(connection)
            if isinstance(error, sqlite3.Error):
                raise _sqlite_error(error) from None
            if isinstance(error, RecoveryError) and error.code in (
                    "CHAIN_CORRUPT", "SCHEMA_CORRUPT", "SCHEMA_UNSUPPORTED", "BINDING_INVALID"):
                # Blocked, never repaired and never resumed from a later record.
                return RecoveryAssessment(
                    state=None, chain_valid=False, action=A.BLOCK_CORRUPT_STATE,
                    reason_codes=("CHAIN_CORRUPT",), last_valid_checkpoint=None,
                    reverification_required=True, **common)
            raise
        latest = history[-1] if history else None
        stored_state = latest.state if latest is not None else None
        state, action, reverify, reason = RECOVERY_DECISIONS[stored_state]
        codes = [reason]
        if action is A.REQUIRE_HUMAN_REVIEW and any(c.state is S.VERIFIED for c in history[:-1]):
            action = A.RETRY_FROM_VERIFIED_CHECKPOINT
            codes.append("EARLIER_VERIFIED_CHECKPOINT")
        return RecoveryAssessment(
            state=state, chain_valid=True, action=action, reason_codes=tuple(codes),
            last_valid_checkpoint=latest, reverification_required=reverify, **common)


def open_recovery_store(configuration, *, clock, id_source):
    """Explicitly open (and create on first use) the trusted recovery store."""
    return RecoveryStore(configuration, clock=clock, id_source=id_source)
