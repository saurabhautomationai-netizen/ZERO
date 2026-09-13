"""G5 ZERO-owned provider-neutral independent-review boundary.

This module turns an independently verified (G3) and durably checkpointed (G4)
attempt into a *bounded review package*, hands that package to an injected
reviewer port, and converts a strictly structured response into an immutable
``ReviewDecision``. It exists because executor-reported success, passing
commands, G3 ``VERIFIED`` evidence and a G4 ``VERIFIED`` checkpoint establish
*observable* facts only. None of them establish that the change is semantically
correct, safe or acceptable. G5 adds that second opinion, and nothing more.

Authority boundaries, stated exactly:

* ZERO remains the source of truth. The reviewer is an advisor with no write
  authority of any kind.
* Reviewer approval is **not** human authorization. A ``PermissionDecision``
  outcome of ``HITL_REQUIRED`` or ``DENIED`` makes zero reviewer calls, and an
  ``APPROVED`` review never satisfies an authenticated human approval.
* Reviewer approval cannot override G3 evidence or G4 durable state. Anything
  other than an exactly bound G3 ``VERIFIED`` verdict plus a valid G4
  ``VERIFIED`` chain is ineligible, and ineligible work is never reviewed.
* G5 never repairs, retries, executes, spawns a process, touches the network,
  reads or writes a file, reads the environment, or updates G4. It produces
  records.
* The controlled execute -> verify -> review loop belongs to G6 orchestration.
  G5 can describe the next remediation as a record; it never runs it.

Trust model, stated honestly:

* SHA-256 fingerprints here are unsigned integrity digests. They detect
  accidental or partial corruption and they bind a response to one exact
  package. They are **not** signatures, authentication, non-repudiation or
  replay protection. Any component able to recompute a payload can recompute
  its digest.
* Reviewer identity comes from injected composition: the ``TrustedReviewerChannel``
  that the application wired up outside task input. It is not proven
  cryptographically, and a response's own claim of identity is never accepted
  as evidence of identity - it must match the channel it arrived on.
* Independence is enforced by trusted configuration and composition (a reviewer
  identity distinct from the executor identity, and a reviewer port with no
  workspace, G4 or milestone access), not by cryptographic authentication and
  not by human judgement.
* Durable replay prevention is deferred: G5 persists nothing, so a response can
  only be rejected as stale within a live evaluation. Persisting review
  decisions would require a G4 change and is out of scope here.

Import is inert: no filesystem, environment, process or network access happens
at import time, and none happens afterwards either - every observation G5 needs
arrives through an injected provider.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol
import hashlib
import json
import re

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, PermissionDecision, TaskPacket, WorkspacePolicy,
    _relative_path, _root,
)
from zero_core.engineering_verification import (
    ChangeObservation, VerificationEvidence, VerificationVerdict,
)
from zero_core.engineering_recovery import (
    RecoveryAction, RecoveryAssessment, RecoveryCheckpoint, RecoveryState,
)


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "ZERO-REVIEW-1"
FINGERPRINT_KIND = "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"
IDENTITY_KIND = "INJECTED_TRUSTED_CHANNEL_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED"
CONTENT_KIND = "UNTRUSTED_ARTIFACT_CONTENT_NOT_INSTRUCTIONS"
INSTRUCTION_AUTHORITY = "ZERO_TRUSTED_CONFIGURATION_ONLY"
DECISION_AUTHORITY = "REVIEW_ONLY_NOT_HUMAN_AUTHORIZATION_NOT_COMPLETION"

MAX_PATH_LENGTH = 1024
MAX_REASON_CODES = 12
MAX_OBJECTIVES = 32
MAX_OBJECTIVE_LENGTH = 64
MAX_LINE_NUMBER = 1000000

# Every rejection, every decision reason and every error code comes from this
# closed vocabulary. No path, prompt, environment value, artifact content or
# provider exception text is ever placed in a code or in an error message.
REASON_CODES = frozenset({
    "REVIEW_APPROVED", "REMEDIATION_REQUIRED",
    "CONFIGURATION_INVALID", "BINDING_INVALID",
    "PERMISSION_DENIED", "HUMAN_AUTHORIZATION_REQUIRED",
    "PROJECT_MISMATCH", "ROOT_MISMATCH", "TASK_MISMATCH", "EXECUTION_MISMATCH",
    "VERIFICATION_NOT_VERIFIED", "EVIDENCE_INVALID", "EVIDENCE_FINGERPRINT_MISMATCH",
    "RECOVERY_STATE_CORRUPT", "RECOVERY_STATE_NOT_VERIFIED", "CHECKPOINT_INVALID",
    "REVIEWER_NOT_INDEPENDENT", "REVIEWER_UNKNOWN", "REVIEWER_ERROR", "REVIEWER_UNAVAILABLE",
    "ARTIFACT_INVALID", "ARTIFACT_PATH_UNTRUSTED", "ARTIFACT_TRUNCATED", "ARTIFACT_LIMIT",
    "PACKAGE_LIMIT", "PACKAGE_FINGERPRINT_MISMATCH",
    "RESPONSE_MALFORMED", "RESPONSE_SCHEMA_INVALID", "RESPONSE_STALE", "RESPONSE_TRUNCATED",
    "REVIEW_TIMEOUT_EXCEEDED", "REQUIRED_DIMENSION_NOT_REVIEWED",
    "FINDING_LIMIT", "FINDING_DUPLICATE", "FINDING_PATH_UNAUTHORIZED",
    "FINDING_ARTIFACT_UNKNOWN", "FINDING_SUMMARY_LIMIT",
    "VERDICT_FINDING_CONTRADICTION",
    "REVIEWER_REPORTED_BLOCKED", "REVIEWER_REPORTED_INCONCLUSIVE",
    "ATTEMPT_LIMIT_EXCEEDED",
})

ERROR_CODES = REASON_CODES


class ReviewError(ValueError):
    """Fixed-code rejection. Carries no path, prose, secret or provider detail."""

    def __init__(self, code="CONFIGURATION_INVALID"):
        if code not in ERROR_CODES:
            code = "CONFIGURATION_INVALID"
        super().__init__(code)
        self.code = code


class ReviewVerdict(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class ReviewDimension(str, Enum):
    CORRECTNESS = "CORRECTNESS"
    SECURITY = "SECURITY"
    BOUNDARY_INTEGRITY = "BOUNDARY_INTEGRITY"
    TEST_ADEQUACY = "TEST_ADEQUACY"
    MAINTAINABILITY = "MAINTAINABILITY"
    DOCUMENTATION = "DOCUMENTATION"


class ReviewArtifactType(str, Enum):
    SOURCE_DIFF = "SOURCE_DIFF"
    SOURCE_TEXT = "SOURCE_TEXT"
    TEST_TEXT = "TEST_TEXT"
    DOCUMENTATION_EXCERPT = "DOCUMENTATION_EXCERPT"
    EVIDENCE_SUMMARY = "EVIDENCE_SUMMARY"


# The single artifact ZERO synthesises itself, from G3 evidence it already
# holds. No provider may supply it, so its content can never be substituted.
SYNTHETIC_ARTIFACT_TYPE = ReviewArtifactType.EVIDENCE_SUMMARY

SEVERITY_ORDER = {
    FindingSeverity.CRITICAL: 0,
    FindingSeverity.HIGH: 1,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.LOW: 3,
    FindingSeverity.INFORMATIONAL: 4,
}

# Fail-closed severity policy. CRITICAL and HIGH remediation-required findings
# can never coexist with APPROVED. MEDIUM is included by default: a reviewer
# that both asks for a code change and approves the change is contradicting
# itself, and ZERO resolves that contradiction by refusing the response rather
# than by picking the more permissive half of it. Trusted configuration may
# narrow the set to CRITICAL/HIGH via ``block_on_medium_remediation=False``,
# which is a deliberate, documented relaxation.
BLOCKING_SEVERITIES = (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
DEFAULT_BLOCKING_SEVERITIES = BLOCKING_SEVERITIES + (FindingSeverity.MEDIUM,)


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ReviewError()
    return value


def _code(value):
    """A bounded machine-readable reason code, not prose."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", value):
        raise ReviewError("RESPONSE_SCHEMA_INVALID")
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ReviewError()
    return value


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ReviewError()
    return value


def _count(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ReviewError()
    return value


def _flag(value):
    if type(value) is not bool:
        raise ReviewError()
    return value


def _line(value):
    """One printable line of bounded text. Control characters are rejected."""
    if not isinstance(value, str) or not value:
        raise ReviewError()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ReviewError()
    return value


def _body(value, limit):
    """Bounded artifact content. Tabs and newlines are the only control bytes."""
    if not isinstance(value, str) or not value:
        raise ReviewError("ARTIFACT_INVALID")
    for character in value:
        code = ord(character)
        if (code < 32 and character not in "\t\n") or code == 127:
            raise ReviewError("ARTIFACT_INVALID")
    if len(value.encode("utf-8")) > limit:
        raise ReviewError("ARTIFACT_LIMIT")
    return value


def _relative(value, code="ARTIFACT_PATH_UNTRUSTED"):
    """Lexical repository-relative path check. No filesystem access happens here.

    ``_relative_path`` already rejects absolute paths, backslashes (and therefore
    UNC and ``\\\\?\\`` device spellings), traversal and empty components, NUL and
    other control bytes, ``:`` (and therefore alternate data streams), wildcard
    and quoting characters, trailing dots, leading or trailing whitespace in a
    component, and Windows device names. Length is bounded on top of that.
    """
    try:
        _relative_path(value)
    except (ValueError, TypeError, AttributeError):
        raise ReviewError(code) from None
    if len(value) > MAX_PATH_LENGTH:
        raise ReviewError(code)
    return value


def _unique_paths(values, code="ARTIFACT_PATH_UNTRUSTED"):
    """Reject duplicates and case-fold collisions; Windows aliases both spellings."""
    if type(values) is not tuple:
        raise ReviewError(code)
    checked = tuple(_relative(value, code) for value in values)
    if len({value.casefold() for value in checked}) != len(checked):
        raise ReviewError(code)
    return tuple(sorted(checked))


def _reason_codes(values):
    if type(values) is not tuple or not values:
        raise ReviewError()
    codes = tuple(sorted(set(values)))
    if len(codes) > MAX_REASON_CODES or any(code not in REASON_CODES for code in codes):
        raise ReviewError()
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
    raise ReviewError()


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


class Record:
    """Canonical JSON only. No pickle, eval or unsafe deserialization anywhere."""

    def canonical_json(self):
        return _canonical(_payload(self))

    def fingerprint(self):
        return _sha256(self.canonical_json())


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdentifierSource(Protocol):
    def next_id(self) -> str: ...


# -- trusted configuration -------------------------------------------------

@dataclass(frozen=True)
class ArtifactSelection(Record):
    """One artifact ZERO will ask the trusted provider for.

    Selections come from trusted configuration only. Neither the TaskPacket, the
    executor, the artifact provider nor the reviewer can add, rename or redirect
    one, so a reviewer can never steer ZERO into reading an arbitrary path.
    """

    artifact_type: ReviewArtifactType
    path: str

    def __post_init__(self):
        if type(self.artifact_type) is not ReviewArtifactType:
            raise ReviewError()
        if self.artifact_type is SYNTHETIC_ARTIFACT_TYPE:
            # The evidence summary is produced by ZERO from G3 evidence, never
            # requested from a provider and never bound to a repository path.
            raise ReviewError()
        _relative(self.path)


@dataclass(frozen=True)
class TrustedReviewConfiguration:
    """Immutable trusted application input, outside all TaskPacket control.

    No TaskPacket, executor output, artifact content or review response can
    reach these fields. The review API accepts no root, no reviewer identity, no
    artifact path and no limit: all of them live here.
    """

    project_id: str
    task_id: str
    execution_id: str
    repository_root: str
    reviewer_id: str
    reviewer_provider_id: str
    protocol_version: str = PROTOCOL_VERSION
    executor_identities: tuple[str, ...] = ()
    authorized_paths: tuple[str, ...] = ()
    artifact_selection: tuple[ArtifactSelection, ...] = ()
    required_dimensions: tuple[ReviewDimension, ...] = ()
    permitted_artifact_types: tuple[ReviewArtifactType, ...] = ()
    include_evidence_summary: bool = True
    max_artifacts: int = 16
    max_artifact_bytes: int = 65536
    max_package_bytes: int = 262144
    max_findings: int = 64
    max_summary_length: int = 512
    review_timeout_seconds: int = 300
    max_response_age_seconds: int = 900
    max_review_attempts: int = 3
    approval_required: bool = True
    human_authorization_required: bool = True
    block_on_medium_remediation: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewError()
        if self.protocol_version != PROTOCOL_VERSION:
            raise ReviewError()
        for value in (self.project_id, self.task_id, self.execution_id,
                      self.reviewer_id, self.reviewer_provider_id):
            _id(value)
        # Lexical only. G5 performs no filesystem access, so canonicality of the
        # root is inherited from the G3/G4 trusted configurations it must match
        # exactly, which removes a time-of-check/time-of-use window here.
        try:
            _root(self.repository_root)
        except (ValueError, TypeError, AttributeError):
            raise ReviewError() from None
        if not isinstance(self.repository_root, str) or len(self.repository_root) > MAX_PATH_LENGTH:
            raise ReviewError()

        if type(self.executor_identities) is not tuple:
            raise ReviewError()
        identities = tuple(sorted({_id(value) for value in self.executor_identities}))
        object.__setattr__(self, "executor_identities", identities)
        if self.reviewer_id in identities or self.reviewer_provider_id in identities:
            # A component cannot independently review its own change.
            raise ReviewError("REVIEWER_NOT_INDEPENDENT")

        object.__setattr__(self, "authorized_paths", _unique_paths(self.authorized_paths))
        if not self.authorized_paths:
            raise ReviewError()

        if type(self.artifact_selection) is not tuple or not self.artifact_selection:
            raise ReviewError()
        for selection in self.artifact_selection:
            if type(selection) is not ArtifactSelection:
                raise ReviewError()
            selection.__post_init__()
            if selection.path not in self.authorized_paths:
                raise ReviewError("ARTIFACT_PATH_UNTRUSTED")
        keys = tuple((s.artifact_type.value, s.path) for s in self.artifact_selection)
        if len(set(keys)) != len(keys):
            raise ReviewError()
        _unique_paths(tuple(s.path for s in self.artifact_selection))
        object.__setattr__(self, "artifact_selection", tuple(sorted(
            self.artifact_selection, key=lambda s: (s.artifact_type.value, s.path))))

        if type(self.required_dimensions) is not tuple or not self.required_dimensions:
            raise ReviewError()
        if any(type(value) is not ReviewDimension for value in self.required_dimensions):
            raise ReviewError()
        object.__setattr__(self, "required_dimensions", tuple(sorted(
            set(self.required_dimensions), key=lambda value: value.value)))

        permitted = self.permitted_artifact_types or tuple(
            sorted({s.artifact_type for s in self.artifact_selection}, key=lambda v: v.value)
        ) + ((SYNTHETIC_ARTIFACT_TYPE,) if self.include_evidence_summary else ())
        if type(permitted) is not tuple or not permitted:
            raise ReviewError()
        if any(type(value) is not ReviewArtifactType for value in permitted):
            raise ReviewError()
        permitted = tuple(sorted(set(permitted), key=lambda value: value.value))
        object.__setattr__(self, "permitted_artifact_types", permitted)
        if any(s.artifact_type not in permitted for s in self.artifact_selection):
            raise ReviewError()
        for value in (self.include_evidence_summary, self.approval_required,
                      self.human_authorization_required, self.block_on_medium_remediation):
            _flag(value)
        if self.include_evidence_summary and SYNTHETIC_ARTIFACT_TYPE not in permitted:
            raise ReviewError()

        _count(self.max_artifacts, 1, 64)
        _count(self.max_artifact_bytes, 64, 1048576)
        _count(self.max_package_bytes, 1024, 4194304)
        _count(self.max_findings, 1, 256)
        _count(self.max_summary_length, 16, 2048)
        _count(self.review_timeout_seconds, 1, 3600)
        _count(self.max_response_age_seconds, 1, 86400)
        _count(self.max_review_attempts, 1, 16)
        if len(self.authorized_paths) > self.max_artifacts * 8:
            raise ReviewError()
        if self.planned_artifact_count() > self.max_artifacts:
            raise ReviewError("ARTIFACT_LIMIT")

    def planned_artifact_count(self):
        return len(self.artifact_selection) + (1 if self.include_evidence_summary else 0)

    def blocking_severities(self):
        return DEFAULT_BLOCKING_SEVERITIES if self.block_on_medium_remediation else BLOCKING_SEVERITIES

    def fingerprint(self):
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["artifact_selection"] = [_payload(value) for value in self.artifact_selection]
        data["required_dimensions"] = [value.value for value in self.required_dimensions]
        data["permitted_artifact_types"] = [value.value for value in self.permitted_artifact_types]
        data["executor_identities"] = list(self.executor_identities)
        data["authorized_paths"] = list(self.authorized_paths)
        return _sha256(_canonical(data))


# -- injected ports --------------------------------------------------------

@dataclass(frozen=True)
class ProvidedArtifact:
    """What a trusted artifact provider returns for one exact selection.

    ``path_state`` is the provider's own filesystem observation. G5 never looks
    at a filesystem, so anything other than an exact ``REGULAR`` report - a
    symlink, a junction, any reparse point, an unavailable or missing path -
    fails closed. ``truncated`` exists so a provider can say "I could not give
    you all of it"; G5 then blocks rather than reviewing a partial diff.
    """

    artifact_type: ReviewArtifactType
    path: str
    content: str
    path_state: str = "REGULAR"
    truncated: bool = False


PATH_STATES = ("REGULAR", "SYMLINK", "REPARSE", "DIRECTORY", "SPECIAL", "MISSING", "UNAVAILABLE")


class ReviewArtifactProvider(Protocol):
    """Trusted, injected. Returns bounded content for one trusted selection."""

    def artifact(self, selection: ArtifactSelection) -> ProvidedArtifact: ...


class IndependentReviewer(Protocol):
    """Provider-neutral reviewer port. Structured in, structured out."""

    def review(self, request: "ReviewRequest") -> "ReviewResponse": ...


@dataclass(frozen=True)
class TrustedReviewerChannel:
    """The injected composition that *is* the reviewer's identity.

    A response's own ``reviewer_id`` is only ever compared against this channel;
    it is never believed on its own. This is configuration-and-composition
    trust, not cryptographic authentication: G5 makes no authenticity,
    non-repudiation or replay-protection claim about a reviewer.
    """

    reviewer_id: str
    reviewer_provider_id: str
    reviewer: IndependentReviewer
    identity_kind: str = IDENTITY_KIND

    def __post_init__(self):
        _id(self.reviewer_id)
        _id(self.reviewer_provider_id)
        if self.identity_kind != IDENTITY_KIND:
            raise ReviewError()
        if self.reviewer is None or not callable(getattr(self.reviewer, "review", None)):
            raise ReviewError("REVIEWER_UNKNOWN")


# -- review package --------------------------------------------------------

@dataclass(frozen=True)
class ReviewArtifact(Record):
    """Bounded, digested, explicitly untrusted review material."""

    artifact_type: ReviewArtifactType
    path: str | None
    byte_length: int
    content_digest: str
    content: str
    content_kind: str = CONTENT_KIND

    def __post_init__(self):
        if type(self.artifact_type) is not ReviewArtifactType:
            raise ReviewError()
        if self.content_kind != CONTENT_KIND:
            raise ReviewError()
        if self.artifact_type is SYNTHETIC_ARTIFACT_TYPE:
            if self.path is not None:
                raise ReviewError()
        else:
            _relative(self.path)
        if not isinstance(self.content, str) or not self.content:
            raise ReviewError("ARTIFACT_INVALID")
        _count(self.byte_length, 1, 1048576)
        if self.byte_length != len(self.content.encode("utf-8")):
            raise ReviewError("ARTIFACT_INVALID")
        if self.content_digest != _sha256(self.content):
            raise ReviewError("ARTIFACT_INVALID")


@dataclass(frozen=True)
class ReviewChangeSummary(Record):
    """G3-observed change sets. Executor claims are deliberately absent."""

    created: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()

    def __post_init__(self):
        for item in fields(self):
            object.__setattr__(self, item.name,
                               _unique_paths(getattr(self, item.name), "EVIDENCE_INVALID"))


@dataclass(frozen=True)
class ReviewCommandEvidence(Record):
    """A G3 verification-command summary and its output digests, never its output."""

    command_id: str
    command_digest: str
    state: str
    exit_code: int | None
    stdout_digest: str | None
    stderr_digest: str | None
    stdout_truncated: bool
    stderr_truncated: bool
    verdict: VerificationVerdict
    reason: str

    def __post_init__(self):
        _id(self.command_id)
        _digest(self.command_digest)
        _line(self.state)
        _line(self.reason)
        if type(self.verdict) is not VerificationVerdict:
            raise ReviewError("EVIDENCE_INVALID")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ReviewError("EVIDENCE_INVALID")
        for value in (self.stdout_digest, self.stderr_digest):
            if value is not None:
                _digest(value)
        _flag(self.stdout_truncated)
        _flag(self.stderr_truncated)


@dataclass(frozen=True)
class ReviewPackage(Record):
    """The exact, deterministic, bounded material an independent reviewer gets.

    Deliberately absent: credentials, secrets, environment mappings, raw prompts,
    conversation or session history, any external agent session identifier,
    unrestricted filesystem content, unbounded command output, executor prose,
    and the absolute repository root (bound here by digest only, so local
    filesystem layout is not disclosed).
    """

    schema_version: int
    protocol_version: str
    review_id: str
    project_id: str
    task_id: str
    execution_id: str
    checkpoint_id: str
    root_digest: str
    authorized_paths: tuple[str, ...]
    packet_fingerprint: str
    policy_fingerprint: str
    decision_fingerprint: str
    execution_fingerprint: str
    evidence_fingerprint: str
    checkpoint_fingerprint: str
    configuration_fingerprint: str
    changes: ReviewChangeSummary
    verification_commands: tuple[ReviewCommandEvidence, ...]
    artifacts: tuple[ReviewArtifact, ...]
    required_dimensions: tuple[ReviewDimension, ...]
    created_at: datetime
    instruction_authority: str = INSTRUCTION_AUTHORITY
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewError()
        if self.protocol_version != PROTOCOL_VERSION or self.fingerprint_kind != FINGERPRINT_KIND:
            raise ReviewError()
        if self.instruction_authority != INSTRUCTION_AUTHORITY:
            raise ReviewError()
        for value in (self.review_id, self.project_id, self.task_id,
                      self.execution_id, self.checkpoint_id):
            _id(value)
        for value in (self.root_digest, self.packet_fingerprint, self.policy_fingerprint,
                      self.decision_fingerprint, self.execution_fingerprint,
                      self.evidence_fingerprint, self.checkpoint_fingerprint,
                      self.configuration_fingerprint):
            _digest(value)
        object.__setattr__(self, "authorized_paths", _unique_paths(self.authorized_paths))
        if type(self.changes) is not ReviewChangeSummary:
            raise ReviewError()
        self.changes.__post_init__()
        if type(self.verification_commands) is not tuple:
            raise ReviewError()
        for command in self.verification_commands:
            if type(command) is not ReviewCommandEvidence:
                raise ReviewError()
            command.__post_init__()
        identifiers = tuple(c.command_id for c in self.verification_commands)
        if len(set(identifiers)) != len(identifiers):
            raise ReviewError("EVIDENCE_INVALID")
        object.__setattr__(self, "verification_commands", tuple(sorted(
            self.verification_commands, key=lambda c: c.command_id)))
        if type(self.artifacts) is not tuple or not self.artifacts:
            raise ReviewError("ARTIFACT_INVALID")
        for artifact in self.artifacts:
            if type(artifact) is not ReviewArtifact:
                raise ReviewError("ARTIFACT_INVALID")
            artifact.__post_init__()
            if artifact.path is not None and artifact.path not in self.authorized_paths:
                raise ReviewError("ARTIFACT_PATH_UNTRUSTED")
        keys = tuple((a.artifact_type.value, a.path or "") for a in self.artifacts)
        if len(set(keys)) != len(keys):
            raise ReviewError("ARTIFACT_INVALID")
        object.__setattr__(self, "artifacts", tuple(sorted(
            self.artifacts, key=lambda a: (a.artifact_type.value, a.path or ""))))
        if type(self.required_dimensions) is not tuple or not self.required_dimensions:
            raise ReviewError()
        if any(type(value) is not ReviewDimension for value in self.required_dimensions):
            raise ReviewError()
        object.__setattr__(self, "required_dimensions", tuple(sorted(
            set(self.required_dimensions), key=lambda value: value.value)))
        _time(self.created_at)

    def artifact_digests(self):
        return frozenset(artifact.content_digest for artifact in self.artifacts)


@dataclass(frozen=True)
class ReviewRequest(Record):
    """Package plus the review contract. Every instruction-bearing field here is
    computed from trusted configuration, never from artifact content."""

    schema_version: int
    protocol_version: str
    reviewer_id: str
    reviewer_provider_id: str
    package: ReviewPackage
    package_fingerprint: str
    required_dimensions: tuple[ReviewDimension, ...]
    verdict_schema: tuple[str, ...]
    severity_schema: tuple[str, ...]
    max_findings: int
    max_summary_length: int
    timeout_seconds: int
    attempt: int
    max_attempts: int
    created_at: datetime
    identity_kind: str = IDENTITY_KIND
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewError()
        if self.protocol_version != PROTOCOL_VERSION or self.fingerprint_kind != FINGERPRINT_KIND:
            raise ReviewError()
        if self.identity_kind != IDENTITY_KIND:
            raise ReviewError()
        _id(self.reviewer_id)
        _id(self.reviewer_provider_id)
        if type(self.package) is not ReviewPackage:
            raise ReviewError()
        self.package.__post_init__()
        if self.package_fingerprint != self.package.fingerprint():
            raise ReviewError("PACKAGE_FINGERPRINT_MISMATCH")
        if type(self.required_dimensions) is not tuple or not self.required_dimensions:
            raise ReviewError()
        if any(type(value) is not ReviewDimension for value in self.required_dimensions):
            raise ReviewError()
        object.__setattr__(self, "required_dimensions", tuple(sorted(
            set(self.required_dimensions), key=lambda value: value.value)))
        if self.required_dimensions != self.package.required_dimensions:
            raise ReviewError()
        if self.verdict_schema != tuple(value.value for value in ReviewVerdict):
            raise ReviewError()
        if self.severity_schema != tuple(value.value for value in FindingSeverity):
            raise ReviewError()
        _count(self.max_findings, 1, 256)
        _count(self.max_summary_length, 16, 2048)
        _count(self.timeout_seconds, 1, 3600)
        _count(self.max_attempts, 1, 16)
        _count(self.attempt, 1, self.max_attempts)
        _time(self.created_at)


# -- review response -------------------------------------------------------

@dataclass(frozen=True)
class ReviewFinding(Record):
    finding_id: str
    severity: FindingSeverity
    reason_code: str
    path: str | None
    line: int | None
    summary: str
    artifact_digest: str | None
    remediation_required: bool

    def __post_init__(self):
        try:
            _id(self.finding_id)
        except ReviewError:
            raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
        if type(self.severity) is not FindingSeverity:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        _code(self.reason_code)
        if self.path is not None:
            _relative(self.path, "FINDING_PATH_UNAUTHORIZED")
        if self.line is not None:
            if type(self.line) is not int or not 1 <= self.line <= MAX_LINE_NUMBER:
                raise ReviewError("RESPONSE_SCHEMA_INVALID")
        if self.line is not None and self.path is None:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        try:
            _line(self.summary)
        except ReviewError:
            raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
        if self.artifact_digest is not None:
            try:
                _digest(self.artifact_digest)
            except ReviewError:
                raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
        if type(self.remediation_required) is not bool:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")

    def sort_key(self):
        return (SEVERITY_ORDER[self.severity], self.path or "", self.line or 0,
                self.reason_code, self.finding_id)

    def identity(self):
        """Content identity, ignoring the reviewer-chosen finding ID."""
        return (self.severity.value, self.reason_code, self.path, self.line,
                self.summary, self.artifact_digest, self.remediation_required)


@dataclass(frozen=True)
class ReviewResponse(Record):
    schema_version: int
    protocol_version: str
    request_fingerprint: str
    package_fingerprint: str
    reviewer_id: str
    reviewer_provider_id: str
    verdict: ReviewVerdict
    findings: tuple[ReviewFinding, ...]
    reviewed_dimensions: tuple[ReviewDimension, ...]
    completed_at: datetime
    truncated: bool = False
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        if self.protocol_version != PROTOCOL_VERSION or self.fingerprint_kind != FINGERPRINT_KIND:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        for value in (self.request_fingerprint, self.package_fingerprint):
            try:
                _digest(value)
            except ReviewError:
                raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
        for value in (self.reviewer_id, self.reviewer_provider_id):
            try:
                _id(value)
            except ReviewError:
                raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
        if type(self.verdict) is not ReviewVerdict:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        if type(self.findings) is not tuple:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        for finding in self.findings:
            if type(finding) is not ReviewFinding:
                raise ReviewError("RESPONSE_SCHEMA_INVALID")
            finding.__post_init__()
        if type(self.reviewed_dimensions) is not tuple:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        if any(type(value) is not ReviewDimension for value in self.reviewed_dimensions):
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        object.__setattr__(self, "reviewed_dimensions", tuple(sorted(
            set(self.reviewed_dimensions), key=lambda value: value.value)))
        if type(self.truncated) is not bool:
            raise ReviewError("RESPONSE_SCHEMA_INVALID")
        try:
            _time(self.completed_at)
        except ReviewError:
            raise ReviewError("RESPONSE_SCHEMA_INVALID") from None


RESPONSE_FIELDS = frozenset(f.name for f in fields(ReviewResponse))
FINDING_FIELDS = frozenset(f.name for f in fields(ReviewFinding))


def parse_review_response(payload) -> ReviewResponse:
    """Strict structured decode. A prose or Markdown reviewer reply is rejected.

    Only a JSON object (or an equivalent mapping) is accepted, with exactly the
    response field names present - unknown fields, missing fields, unknown enum
    values and malformed timestamps all fail closed. There is no Markdown, prose
    or regular-expression path to a verdict anywhere in this module.
    """
    data = payload
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            raise ReviewError("RESPONSE_MALFORMED") from None
    if type(data) is not dict:
        raise ReviewError("RESPONSE_MALFORMED")
    if frozenset(data) != RESPONSE_FIELDS:
        raise ReviewError("RESPONSE_SCHEMA_INVALID")
    values = dict(data)
    try:
        values["verdict"] = ReviewVerdict(values["verdict"])
        values["reviewed_dimensions"] = tuple(
            ReviewDimension(value) for value in _sequence(values["reviewed_dimensions"]))
        values["completed_at"] = _decode_time(values["completed_at"])
        values["findings"] = tuple(
            _decode_finding(value) for value in _sequence(values["findings"]))
    except (ValueError, TypeError, KeyError) as error:
        if isinstance(error, ReviewError):
            raise
        raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
    try:
        return ReviewResponse(**values)
    except ReviewError:
        raise
    except (ValueError, TypeError):
        raise ReviewError("RESPONSE_SCHEMA_INVALID") from None


def _sequence(value):
    if type(value) not in (list, tuple):
        raise ReviewError("RESPONSE_SCHEMA_INVALID")
    return tuple(value)


def _decode_time(value):
    if not isinstance(value, str):
        raise ReviewError("RESPONSE_SCHEMA_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ReviewError("RESPONSE_SCHEMA_INVALID")
    return parsed


def _decode_finding(value):
    if type(value) is not dict or frozenset(value) != FINDING_FIELDS:
        raise ReviewError("RESPONSE_SCHEMA_INVALID")
    values = dict(value)
    try:
        values["severity"] = FindingSeverity(values["severity"])
    except (ValueError, TypeError, KeyError):
        raise ReviewError("RESPONSE_SCHEMA_INVALID") from None
    try:
        return ReviewFinding(**values)
    except ReviewError:
        raise
    except (ValueError, TypeError):
        raise ReviewError("RESPONSE_SCHEMA_INVALID") from None


# -- decision and remediation ---------------------------------------------

@dataclass(frozen=True)
class ReviewDecision(Record):
    """ZERO's own immutable conclusion about one review.

    ``authority`` is a constant, and there is no field, method or code path here
    that marks anything complete, grants a human approval, or writes G4.
    """

    schema_version: int
    protocol_version: str
    decision_id: str
    project_id: str
    task_id: str
    execution_id: str
    checkpoint_id: str | None
    review_id: str | None
    configuration_fingerprint: str
    request_fingerprint: str | None
    response_fingerprint: str | None
    package_fingerprint: str | None
    evidence_fingerprint: str | None
    checkpoint_fingerprint: str | None
    reviewer_id: str
    reviewer_provider_id: str
    verdict: ReviewVerdict
    reason_codes: tuple[str, ...]
    findings: tuple[ReviewFinding, ...]
    reviewed_dimensions: tuple[ReviewDimension, ...]
    remediation_required: bool
    human_review_required: bool
    attempt: int
    max_attempts: int
    decided_at: datetime
    authorizes_execution: bool = False
    authority: str = DECISION_AUTHORITY
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewError()
        if self.protocol_version != PROTOCOL_VERSION or self.fingerprint_kind != FINGERPRINT_KIND:
            raise ReviewError()
        if self.authority != DECISION_AUTHORITY or self.authorizes_execution is not False:
            raise ReviewError()
        for value in (self.decision_id, self.project_id, self.task_id,
                      self.execution_id, self.reviewer_id, self.reviewer_provider_id):
            _id(value)
        for value in (self.checkpoint_id, self.review_id):
            if value is not None:
                _id(value)
        _digest(self.configuration_fingerprint)
        for value in (self.request_fingerprint, self.response_fingerprint,
                      self.package_fingerprint, self.evidence_fingerprint,
                      self.checkpoint_fingerprint):
            if value is not None:
                _digest(value)
        if type(self.verdict) is not ReviewVerdict:
            raise ReviewError()
        object.__setattr__(self, "reason_codes", _reason_codes(self.reason_codes))
        if type(self.findings) is not tuple:
            raise ReviewError()
        for finding in self.findings:
            if type(finding) is not ReviewFinding:
                raise ReviewError()
            finding.__post_init__()
        identifiers = tuple(finding.finding_id for finding in self.findings)
        if len(set(identifiers)) != len(identifiers):
            raise ReviewError("FINDING_DUPLICATE")
        object.__setattr__(self, "findings",
                           tuple(sorted(self.findings, key=lambda f: f.sort_key())))
        if type(self.reviewed_dimensions) is not tuple:
            raise ReviewError()
        if any(type(value) is not ReviewDimension for value in self.reviewed_dimensions):
            raise ReviewError()
        object.__setattr__(self, "reviewed_dimensions", tuple(sorted(
            set(self.reviewed_dimensions), key=lambda value: value.value)))
        for value in (self.remediation_required, self.human_review_required):
            _flag(value)
        _count(self.max_attempts, 1, 16)
        _count(self.attempt, 1, self.max_attempts)
        _time(self.decided_at)
        # Fail-closed invariants that hold for every decision this module emits.
        if self.verdict is ReviewVerdict.APPROVED:
            if self.remediation_required or any(f.remediation_required for f in self.findings):
                raise ReviewError("VERDICT_FINDING_CONTRADICTION")
            if any(f.severity in DEFAULT_BLOCKING_SEVERITIES for f in self.findings
                   if f.remediation_required):
                raise ReviewError("VERDICT_FINDING_CONTRADICTION")
            if self.request_fingerprint is None or self.response_fingerprint is None:
                raise ReviewError()
            if self.reason_codes != ("REVIEW_APPROVED",):
                raise ReviewError()
        if self.verdict is ReviewVerdict.CHANGES_REQUESTED and not any(
                f.remediation_required for f in self.findings):
            raise ReviewError("VERDICT_FINDING_CONTRADICTION")


@dataclass(frozen=True)
class RemediationRequest(Record):
    """A bounded description of what G6 may ask an executor to fix next.

    Creating one performs no execution, calls no executor, touches no
    workspace, updates no G4 state and requests no further review.
    """

    schema_version: int
    protocol_version: str
    remediation_id: str
    project_id: str
    task_id: str
    execution_id: str
    review_id: str
    previous_review_fingerprint: str
    target_paths: tuple[str, ...]
    finding_ids: tuple[str, ...]
    objectives: tuple[str, ...]
    next_attempt: int
    max_attempts: int
    created_at: datetime
    fingerprint_kind: str = FINGERPRINT_KIND

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewError()
        if self.protocol_version != PROTOCOL_VERSION or self.fingerprint_kind != FINGERPRINT_KIND:
            raise ReviewError()
        for value in (self.remediation_id, self.project_id, self.task_id,
                      self.execution_id, self.review_id):
            _id(value)
        _digest(self.previous_review_fingerprint)
        object.__setattr__(self, "target_paths", _unique_paths(self.target_paths))
        if not self.target_paths:
            raise ReviewError()
        if type(self.finding_ids) is not tuple or not self.finding_ids:
            raise ReviewError()
        identifiers = tuple(_id(value) for value in self.finding_ids)
        if len(set(identifiers)) != len(identifiers):
            raise ReviewError("FINDING_DUPLICATE")
        object.__setattr__(self, "finding_ids", tuple(sorted(identifiers)))
        if type(self.objectives) is not tuple or not self.objectives:
            raise ReviewError()
        objectives = tuple(sorted({_code(value) for value in self.objectives}))
        if len(objectives) > MAX_OBJECTIVES or any(
                len(value) > MAX_OBJECTIVE_LENGTH for value in objectives):
            raise ReviewError()
        object.__setattr__(self, "objectives", objectives)
        _count(self.max_attempts, 1, 16)
        _count(self.next_attempt, 2, self.max_attempts)
        _time(self.created_at)


def _derived_id(prefix, data):
    return "%s-%s" % (prefix, _sha256(_canonical(data))[:32])


# -- the boundary ----------------------------------------------------------

@dataclass(frozen=True)
class IndependentReviewBoundary:
    """ZERO's review gate. Everything crossing it is injected and bounded.

    The eligibility gate runs *before* any reviewer or provider call, so an
    ineligible attempt produces zero reviewer calls. Independent review can
    therefore never convert ineligible work into approved work.
    """

    configuration: TrustedReviewConfiguration
    channel: TrustedReviewerChannel
    artifacts: ReviewArtifactProvider
    clock: Clock
    id_source: IdentifierSource

    def __post_init__(self):
        config = self.configuration
        if type(config) is not TrustedReviewConfiguration:
            raise ReviewError()
        config.__post_init__()
        if type(self.channel) is not TrustedReviewerChannel:
            raise ReviewError("REVIEWER_UNKNOWN")
        self.channel.__post_init__()
        if (self.channel.reviewer_id, self.channel.reviewer_provider_id) != (
                config.reviewer_id, config.reviewer_provider_id):
            # Identity is the injected channel, checked against trusted config.
            raise ReviewError("REVIEWER_UNKNOWN")
        if self.artifacts is None or not callable(getattr(self.artifacts, "artifact", None)):
            raise ReviewError()
        if not callable(getattr(self.clock, "now", None)):
            raise ReviewError()
        if not callable(getattr(self.id_source, "next_id", None)):
            raise ReviewError()

    # -- eligibility -------------------------------------------------------

    def check_eligibility(self, *, packet, policy, decision, execution, evidence,
                          checkpoint, assessment):
        """Fail closed unless every G1-G4 authority agrees, exactly.

        Raises ``ReviewError`` with a bounded code. Makes no reviewer call, no
        artifact-provider call and no observation of any kind.
        """
        config = self.configuration
        config.__post_init__()
        self.__post_init__()

        try:
            packet = TaskPacket.model_validate(packet)
            policy = WorkspacePolicy.model_validate(policy)
            if type(decision) is not PermissionDecision:
                raise ValueError()
            decision.validate_binding(packet, policy)
        except (ValueError, TypeError, AttributeError, OSError):
            raise ReviewError("BINDING_INVALID") from None

        if decision.outcome == "DENIED":
            raise ReviewError("PERMISSION_DENIED")
        if decision.outcome == "HITL_REQUIRED":
            # Authenticated human approval is a separate authority. G5 does not
            # stand in for it, so it does not even ask the reviewer.
            raise ReviewError("HUMAN_AUTHORIZATION_REQUIRED")
        if decision.outcome != "LOW_RISK":
            raise ReviewError("BINDING_INVALID")

        if packet.project_id != config.project_id or policy.project_id != config.project_id:
            raise ReviewError("PROJECT_MISMATCH")
        # A task-controlled root can never widen or replace the trusted root.
        if packet.repository_root != config.repository_root or policy.repository_root != config.repository_root:
            raise ReviewError("ROOT_MISMATCH")
        if packet.task_id != config.task_id:
            raise ReviewError("TASK_MISMATCH")

        try:
            if type(execution) is not EngineeringExecutionResult:
                raise ValueError()
            execution.validate_binding(packet, decision, policy)
        except (ValueError, TypeError, AttributeError, OSError):
            raise ReviewError("BINDING_INVALID") from None
        if execution.project_id != config.project_id:
            raise ReviewError("PROJECT_MISMATCH")
        if execution.task_id != config.task_id:
            raise ReviewError("TASK_MISMATCH")
        if execution.execution_id != config.execution_id:
            raise ReviewError("EXECUTION_MISMATCH")
        if execution.executor_id in (config.reviewer_id, config.reviewer_provider_id):
            raise ReviewError("REVIEWER_NOT_INDEPENDENT")

        try:
            if type(evidence) is not VerificationEvidence:
                raise ValueError()
            evidence.__post_init__()
            binding = evidence.binding
            binding.__post_init__()
        except (ValueError, TypeError, AttributeError, OSError):
            raise ReviewError("EVIDENCE_INVALID") from None
        if binding.project_id != config.project_id:
            raise ReviewError("PROJECT_MISMATCH")
        if binding.repository_root != config.repository_root:
            raise ReviewError("ROOT_MISMATCH")
        if binding.task_id != config.task_id:
            raise ReviewError("TASK_MISMATCH")
        if binding.execution_id != config.execution_id:
            raise ReviewError("EXECUTION_MISMATCH")
        if (binding.packet_digest, binding.policy_digest, binding.decision_digest) != (
                packet.fingerprint(), policy.fingerprint(), decision.fingerprint()):
            raise ReviewError("BINDING_INVALID")
        if evidence.execution_digest != execution.fingerprint():
            raise ReviewError("BINDING_INVALID")
        if evidence.verdict is not VerificationVerdict.VERIFIED:
            # FAILED, BLOCKED and INCONCLUSIVE are all ineligible for review.
            raise ReviewError("VERIFICATION_NOT_VERIFIED")

        try:
            if type(assessment) is not RecoveryAssessment:
                raise ValueError()
            assessment.__post_init__()
            if type(checkpoint) is not RecoveryCheckpoint:
                raise ValueError()
            checkpoint.__post_init__()
        except (ValueError, TypeError, AttributeError, OSError):
            raise ReviewError("RECOVERY_STATE_CORRUPT") from None
        if not assessment.chain_valid or assessment.action is RecoveryAction.BLOCK_CORRUPT_STATE:
            raise ReviewError("RECOVERY_STATE_CORRUPT")
        if (assessment.project_id, assessment.task_id, assessment.execution_id) != (
                config.project_id, config.task_id, config.execution_id):
            raise ReviewError("BINDING_INVALID")
        if assessment.state is not RecoveryState.VERIFIED:
            # INTERRUPTED, REQUIRES_REVERIFICATION and every other durable state
            # mean the recovery record does not correspond to VERIFIED work.
            raise ReviewError("RECOVERY_STATE_NOT_VERIFIED")
        if assessment.reverification_required or assessment.action is not RecoveryAction.NO_ACTION:
            raise ReviewError("RECOVERY_STATE_NOT_VERIFIED")
        if assessment.last_valid_checkpoint != checkpoint:
            raise ReviewError("CHECKPOINT_INVALID")

        if checkpoint.state is not RecoveryState.VERIFIED:
            raise ReviewError("RECOVERY_STATE_NOT_VERIFIED")
        if checkpoint.project_id != config.project_id:
            raise ReviewError("PROJECT_MISMATCH")
        if checkpoint.repository_root != config.repository_root:
            raise ReviewError("ROOT_MISMATCH")
        if checkpoint.task_id != config.task_id:
            raise ReviewError("TASK_MISMATCH")
        if checkpoint.execution_id != config.execution_id:
            raise ReviewError("EXECUTION_MISMATCH")
        if (checkpoint.packet_fingerprint, checkpoint.policy_fingerprint,
                checkpoint.decision_fingerprint) != (
                packet.fingerprint(), policy.fingerprint(), decision.fingerprint()):
            raise ReviewError("BINDING_INVALID")
        if checkpoint.attempt_fingerprint != execution.fingerprint():
            raise ReviewError("BINDING_INVALID")
        if checkpoint.evidence_fingerprint != evidence.fingerprint():
            # Stale or substituted evidence: the durable record and the evidence
            # offered for review are not the same observation.
            raise ReviewError("EVIDENCE_FINGERPRINT_MISMATCH")
        return packet, policy, decision, execution, evidence, checkpoint, assessment

    # -- artifacts ---------------------------------------------------------

    def _evidence_artifact(self, evidence):
        """ZERO's own bounded structured summary of the G3 evidence record."""
        content = _canonical({
            "evidence_fingerprint": evidence.fingerprint(),
            "verdict": evidence.verdict.value,
            "reason_codes": list(evidence.reason_codes),
            "created_at": evidence.created_at.isoformat(),
            "changes": _payload(_change_summary(evidence.changes)),
            "commands": [_payload(item) for item in _command_evidence(evidence)],
            "fingerprint_kind": evidence.fingerprint_kind,
        })
        _body(content, self.configuration.max_artifact_bytes)
        return ReviewArtifact(SYNTHETIC_ARTIFACT_TYPE, None, len(content.encode("utf-8")),
                              _sha256(content), content)

    def _provided_artifacts(self, evidence):
        config = self.configuration
        if config.planned_artifact_count() > config.max_artifacts:
            raise ReviewError("ARTIFACT_LIMIT")
        collected = tuple(self._one_artifact(selection) for selection in config.artifact_selection)
        if config.include_evidence_summary:
            collected = collected + (self._evidence_artifact(evidence),)
        if len(collected) > config.max_artifacts:
            raise ReviewError("ARTIFACT_LIMIT")
        _unique_paths(tuple(a.path for a in collected if a.path is not None))
        total = sum(artifact.byte_length for artifact in collected)
        if total > config.max_package_bytes:
            raise ReviewError("PACKAGE_LIMIT")
        return collected

    def _one_artifact(self, selection):
        config = self.configuration
        try:
            provided = self.artifacts.artifact(selection)
        except ReviewError:
            raise
        except Exception:
            # Never surface a provider exception, path or message.
            raise ReviewError("ARTIFACT_INVALID") from None
        if type(provided) is not ProvidedArtifact:
            raise ReviewError("ARTIFACT_INVALID")
        if provided.artifact_type is not selection.artifact_type:
            raise ReviewError("ARTIFACT_INVALID")
        if provided.path != selection.path:
            # An unexpected path is a boundary violation, not a substitution.
            raise ReviewError("ARTIFACT_PATH_UNTRUSTED")
        if provided.artifact_type not in config.permitted_artifact_types:
            raise ReviewError("ARTIFACT_INVALID")
        if provided.path_state not in PATH_STATES:
            raise ReviewError("ARTIFACT_PATH_UNTRUSTED")
        if provided.path_state != "REGULAR":
            # Symlink, junction, reparse point, directory, device, missing or
            # unavailable: all ambiguous, all fail closed.
            raise ReviewError("ARTIFACT_PATH_UNTRUSTED")
        if type(provided.truncated) is not bool:
            raise ReviewError("ARTIFACT_INVALID")
        if provided.truncated:
            # Source and diffs are never silently shortened for a reviewer.
            raise ReviewError("ARTIFACT_TRUNCATED")
        _relative(provided.path)
        if provided.path not in config.authorized_paths:
            raise ReviewError("ARTIFACT_PATH_UNTRUSTED")
        content = _body(provided.content, config.max_artifact_bytes)
        return ReviewArtifact(provided.artifact_type, provided.path,
                              len(content.encode("utf-8")), _sha256(content), content)

    # -- request -----------------------------------------------------------

    def create_request(self, *, packet, policy, decision, execution, evidence,
                       checkpoint, assessment, attempt=1) -> ReviewRequest:
        """Build the bounded review package. Ineligible work raises instead."""
        config = self.configuration
        _count(attempt, 1, config.max_review_attempts)
        (packet, policy, decision, execution, evidence, checkpoint,
         assessment) = self.check_eligibility(
            packet=packet, policy=policy, decision=decision, execution=execution,
            evidence=evidence, checkpoint=checkpoint, assessment=assessment)

        collected = self._provided_artifacts(evidence)
        created = self.clock.now()
        _time(created)
        review_id = _id(self.id_source.next_id())
        package = ReviewPackage(
            schema_version=SCHEMA_VERSION, protocol_version=PROTOCOL_VERSION,
            review_id=review_id, project_id=config.project_id, task_id=config.task_id,
            execution_id=config.execution_id, checkpoint_id=checkpoint.checkpoint_id,
            root_digest=_sha256(config.repository_root),
            authorized_paths=config.authorized_paths,
            packet_fingerprint=packet.fingerprint(), policy_fingerprint=policy.fingerprint(),
            decision_fingerprint=decision.fingerprint(),
            execution_fingerprint=execution.fingerprint(),
            evidence_fingerprint=evidence.fingerprint(),
            checkpoint_fingerprint=checkpoint.fingerprint(),
            configuration_fingerprint=config.fingerprint(),
            changes=_change_summary(evidence.changes),
            verification_commands=_command_evidence(evidence),
            artifacts=collected, required_dimensions=config.required_dimensions,
            created_at=created)
        if len(package.canonical_json().encode("utf-8")) > config.max_package_bytes:
            raise ReviewError("PACKAGE_LIMIT")
        request = ReviewRequest(
            schema_version=SCHEMA_VERSION, protocol_version=PROTOCOL_VERSION,
            reviewer_id=config.reviewer_id, reviewer_provider_id=config.reviewer_provider_id,
            package=package, package_fingerprint=package.fingerprint(),
            required_dimensions=config.required_dimensions,
            verdict_schema=tuple(value.value for value in ReviewVerdict),
            severity_schema=tuple(value.value for value in FindingSeverity),
            max_findings=config.max_findings, max_summary_length=config.max_summary_length,
            timeout_seconds=config.review_timeout_seconds, attempt=attempt,
            max_attempts=config.max_review_attempts, created_at=created)
        request.fingerprint()  # validate the whole canonical payload before use
        return request

    # -- invocation and evaluation ----------------------------------------

    def review(self, *, packet, policy, decision, execution, evidence, checkpoint,
               assessment, attempt=1) -> ReviewDecision:
        """Gate, package, ask the injected reviewer, and decide.

        An ineligible attempt returns a BLOCKED decision without ever reaching
        the reviewer. A reviewer failure, timeout or malformed answer can never
        return APPROVED.
        """
        try:
            request = self.create_request(
                packet=packet, policy=policy, decision=decision, execution=execution,
                evidence=evidence, checkpoint=checkpoint, assessment=assessment,
                attempt=attempt)
        except ReviewError as error:
            return self._blocked(error.code, attempt=attempt)
        try:
            raw = self.channel.reviewer.review(request)
        except TimeoutError:
            return self._terminal(ReviewVerdict.INCONCLUSIVE, ("REVIEWER_UNAVAILABLE",),
                                  request=request, attempt=attempt)
        except BaseException:
            # No provider exception text, traceback or partial answer escapes.
            return self._terminal(ReviewVerdict.BLOCKED, ("REVIEWER_ERROR",),
                                  request=request, attempt=attempt)
        return self.evaluate_response(request, raw, attempt=attempt)

    def evaluate_response(self, request, raw, *, attempt=None) -> ReviewDecision:
        """Validate one answer against one exact package and decide.

        Deterministic and idempotent: evaluating the same immutable request and
        response again produces a byte-identical decision.
        """
        if type(request) is not ReviewRequest:
            raise ReviewError("BINDING_INVALID")
        request.__post_init__()
        attempt = request.attempt if attempt is None else _count(attempt, 1, request.max_attempts)
        if attempt != request.attempt:
            raise ReviewError("BINDING_INVALID")
        config = self.configuration
        config.__post_init__()
        if request.package.configuration_fingerprint != config.fingerprint():
            raise ReviewError("BINDING_INVALID")

        try:
            response = raw if type(raw) is ReviewResponse else parse_review_response(raw)
            response.__post_init__()
        except ReviewError as error:
            code = error.code if error.code in REASON_CODES else "RESPONSE_MALFORMED"
            return self._terminal(ReviewVerdict.BLOCKED, (code,), request=request, attempt=attempt)
        except Exception:
            return self._terminal(ReviewVerdict.BLOCKED, ("RESPONSE_MALFORMED",),
                                  request=request, attempt=attempt)

        blocking, inconclusive = self._response_problems(request, response)
        if blocking:
            return self._terminal(ReviewVerdict.BLOCKED, blocking, request=request,
                                  response=response, attempt=attempt)
        if inconclusive:
            return self._terminal(ReviewVerdict.INCONCLUSIVE, inconclusive, request=request,
                                  response=response, attempt=attempt)
        if response.verdict is ReviewVerdict.APPROVED:
            return self._terminal(ReviewVerdict.APPROVED, ("REVIEW_APPROVED",), request=request,
                                  response=response, attempt=attempt)
        return self._terminal(ReviewVerdict.CHANGES_REQUESTED, ("REMEDIATION_REQUIRED",),
                              request=request, response=response, attempt=attempt)

    def _response_problems(self, request, response):
        """Return (blocking, inconclusive) bounded reason codes, both ordered."""
        config = self.configuration
        package = request.package
        blocking = ()
        inconclusive = ()

        if response.request_fingerprint != request.fingerprint() or (
                response.package_fingerprint != package.fingerprint()):
            # Covers a stale package, older G3 evidence, an older G4 checkpoint
            # and any attempt to replay a response across task, execution,
            # project or root: all of them change the package fingerprint.
            blocking = blocking + ("PACKAGE_FINGERPRINT_MISMATCH",)
        if (response.reviewer_id, response.reviewer_provider_id) != (
                self.channel.reviewer_id, self.channel.reviewer_provider_id):
            blocking = blocking + ("REVIEWER_UNKNOWN",)
        if response.protocol_version != PROTOCOL_VERSION or response.schema_version != SCHEMA_VERSION:
            blocking = blocking + ("RESPONSE_SCHEMA_INVALID",)

        findings = response.findings
        if len(findings) > min(config.max_findings, request.max_findings):
            blocking = blocking + ("FINDING_LIMIT",)
        identifiers = tuple(finding.finding_id for finding in findings)
        if len(set(identifiers)) != len(identifiers):
            blocking = blocking + ("FINDING_DUPLICATE",)
        contents = tuple(finding.identity() for finding in findings)
        if len(set(contents)) != len(contents):
            blocking = blocking + ("FINDING_DUPLICATE",)
        if any(len(finding.summary) > min(config.max_summary_length, request.max_summary_length)
               for finding in findings):
            blocking = blocking + ("FINDING_SUMMARY_LIMIT",)
        if any(finding.path is not None and finding.path not in package.authorized_paths
               for finding in findings):
            blocking = blocking + ("FINDING_PATH_UNAUTHORIZED",)
        digests = package.artifact_digests()
        if any(finding.artifact_digest is not None and finding.artifact_digest not in digests
               for finding in findings):
            blocking = blocking + ("FINDING_ARTIFACT_UNKNOWN",)

        now = self.clock.now()
        _time(now)
        if response.completed_at < request.created_at or response.completed_at > now:
            blocking = blocking + ("RESPONSE_STALE",)
        elif (now - response.completed_at).total_seconds() > config.max_response_age_seconds:
            blocking = blocking + ("RESPONSE_STALE",)

        if response.verdict is ReviewVerdict.BLOCKED:
            blocking = blocking + ("REVIEWER_REPORTED_BLOCKED",)

        remediation = tuple(f for f in findings if f.remediation_required)
        severities = config.blocking_severities()
        if response.verdict is ReviewVerdict.APPROVED and remediation:
            # A reviewer cannot both require a code change and approve the work.
            blocking = blocking + ("VERDICT_FINDING_CONTRADICTION",)
        if response.verdict is ReviewVerdict.APPROVED and any(
                f.severity in severities for f in findings):
            blocking = blocking + ("VERDICT_FINDING_CONTRADICTION",)
        if response.verdict is ReviewVerdict.CHANGES_REQUESTED and not remediation:
            blocking = blocking + ("VERDICT_FINDING_CONTRADICTION",)

        if response.truncated:
            inconclusive = inconclusive + ("RESPONSE_TRUNCATED",)
        if not set(request.required_dimensions) <= set(response.reviewed_dimensions):
            inconclusive = inconclusive + ("REQUIRED_DIMENSION_NOT_REVIEWED",)
        if (response.completed_at - request.created_at).total_seconds() > request.timeout_seconds:
            inconclusive = inconclusive + ("REVIEW_TIMEOUT_EXCEEDED",)
        if response.verdict is ReviewVerdict.INCONCLUSIVE:
            inconclusive = inconclusive + ("REVIEWER_REPORTED_INCONCLUSIVE",)
        return tuple(sorted(set(blocking))), tuple(sorted(set(inconclusive)))

    # -- decision construction --------------------------------------------

    def _blocked(self, code, *, attempt):
        return self._terminal(ReviewVerdict.BLOCKED, (code,), attempt=attempt)

    def _terminal(self, verdict, reasons, *, request=None, response=None, attempt):
        config = self.configuration
        package = request.package if request is not None else None
        findings = response.findings if response is not None else ()
        dimensions = response.reviewed_dimensions if response is not None else ()
        if verdict is ReviewVerdict.BLOCKED:
            # A blocked response is untrusted in whole, not in part: none of its
            # findings or claimed dimensions are carried into the decision.
            findings, dimensions = (), ()
        if verdict is ReviewVerdict.APPROVED:
            findings = tuple(f for f in findings if not f.remediation_required)
        remediation = any(f.remediation_required for f in findings)
        human = True if verdict is not ReviewVerdict.APPROVED else config.human_authorization_required
        request_fingerprint = request.fingerprint() if request is not None else None
        response_fingerprint = response.fingerprint() if response is not None else None
        decided = self.clock.now()
        _time(decided)
        codes = _reason_codes(reasons)
        seed = {
            "configuration": config.fingerprint(),
            "request": request_fingerprint,
            "response": response_fingerprint,
            "verdict": verdict.value,
            "reason_codes": list(codes),
            "attempt": attempt,
            "decided_at": decided.isoformat(),
        }
        decision = ReviewDecision(
            schema_version=SCHEMA_VERSION, protocol_version=PROTOCOL_VERSION,
            decision_id=_derived_id("review-decision", seed),
            project_id=config.project_id, task_id=config.task_id,
            execution_id=config.execution_id,
            checkpoint_id=package.checkpoint_id if package is not None else None,
            review_id=package.review_id if package is not None else None,
            configuration_fingerprint=config.fingerprint(),
            request_fingerprint=request_fingerprint,
            response_fingerprint=response_fingerprint,
            package_fingerprint=package.fingerprint() if package is not None else None,
            evidence_fingerprint=package.evidence_fingerprint if package is not None else None,
            checkpoint_fingerprint=package.checkpoint_fingerprint if package is not None else None,
            reviewer_id=config.reviewer_id, reviewer_provider_id=config.reviewer_provider_id,
            verdict=verdict, reason_codes=codes, findings=findings,
            reviewed_dimensions=dimensions, remediation_required=remediation,
            human_review_required=human, attempt=attempt,
            max_attempts=config.max_review_attempts, decided_at=decided)
        decision.fingerprint()  # validate the whole canonical payload before use
        return decision

    # -- remediation boundary ---------------------------------------------

    def remediation_request(self, decision) -> RemediationRequest:
        """Describe the next attempt. This runs nothing and schedules nothing."""
        config = self.configuration
        if type(decision) is not ReviewDecision:
            raise ReviewError("BINDING_INVALID")
        decision.__post_init__()
        if decision.configuration_fingerprint != config.fingerprint():
            raise ReviewError("BINDING_INVALID")
        if decision.verdict is not ReviewVerdict.CHANGES_REQUESTED:
            raise ReviewError("VERDICT_FINDING_CONTRADICTION")
        if decision.review_id is None or decision.response_fingerprint is None:
            raise ReviewError("BINDING_INVALID")
        actionable = tuple(f for f in decision.findings if f.remediation_required)
        if not actionable:
            raise ReviewError("VERDICT_FINDING_CONTRADICTION")
        next_attempt = decision.attempt + 1
        if next_attempt > config.max_review_attempts:
            # The controlled loop stops here. G6 decides what happens next.
            raise ReviewError("ATTEMPT_LIMIT_EXCEEDED")
        paths = tuple(f.path for f in actionable if f.path is not None)
        if not paths:
            raise ReviewError("FINDING_PATH_UNAUTHORIZED")
        if any(path not in config.authorized_paths for path in paths):
            raise ReviewError("FINDING_PATH_UNAUTHORIZED")
        created = self.clock.now()
        _time(created)
        objectives = tuple(sorted({f.reason_code for f in actionable}))
        seed = {
            "configuration": config.fingerprint(),
            "review": decision.review_id,
            "response": decision.response_fingerprint,
            "next_attempt": next_attempt,
        }
        remediation = RemediationRequest(
            schema_version=SCHEMA_VERSION, protocol_version=PROTOCOL_VERSION,
            remediation_id=_derived_id("remediation", seed),
            project_id=config.project_id, task_id=config.task_id,
            execution_id=config.execution_id, review_id=decision.review_id,
            previous_review_fingerprint=decision.response_fingerprint,
            target_paths=tuple(sorted(set(paths))),
            finding_ids=tuple(sorted({f.finding_id for f in actionable})),
            objectives=objectives, next_attempt=next_attempt,
            max_attempts=config.max_review_attempts, created_at=created)
        remediation.fingerprint()
        return remediation


def _change_summary(changes) -> ReviewChangeSummary:
    if type(changes) is not ChangeObservation:
        raise ReviewError("EVIDENCE_INVALID")
    changes.__post_init__()
    return ReviewChangeSummary(created=changes.created, modified=changes.modified,
                               deleted=changes.deleted, unexpected=changes.unexpected,
                               unsupported=changes.unsupported)


def _command_evidence(evidence) -> tuple:
    return tuple(sorted(
        (ReviewCommandEvidence(
            command_id=test.command_id, command_digest=test.command_digest, state=test.state,
            exit_code=test.exit_code, stdout_digest=test.stdout_digest,
            stderr_digest=test.stderr_digest, stdout_truncated=test.stdout_truncated,
            stderr_truncated=test.stderr_truncated, verdict=test.verdict, reason=test.reason)
         for test in evidence.tests),
        key=lambda item: item.command_id))


def open_review_boundary(configuration, *, channel, artifacts, clock, id_source):
    """Explicitly compose the review boundary from trusted, injected parts."""
    return IndependentReviewBoundary(configuration=configuration, channel=channel,
                                     artifacts=artifacts, clock=clock, id_source=id_source)
