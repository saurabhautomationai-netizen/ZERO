"""Pure G1 boundary records. No runtime imports or execution authority.

Use validated construction/model_validate_json, never model_construct, at trust
boundaries. Paths are checked lexically; G2 must resolve and enforce containment.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.functional_validators import AfterValidator


PermissionOutcome = Literal["LOW_RISK", "HITL_REQUIRED", "DENIED"]
OperationType = Literal["READ_FILE", "CREATE_FILE", "MODIFY_FILE", "DELETE_FILE", "RUN_COMMAND"]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")]
Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _relative_path(value: str) -> str:
    """One portable spelling, including Windows restrictions on all platforms."""
    if not value or value.startswith("/") or "\\" in value:
        raise ValueError("expected a normalized repository-relative path")
    if any(ord(c) < 32 or ord(c) == 127 or c in ':<>"|?*%' for c in value):
        raise ValueError("unsafe or ambiguous path character")
    for part in value.split("/"):
        if part in ("", ".", "..") or part != part.strip() or part.endswith("."):
            raise ValueError("empty, traversal, or ambiguous path component")
        stem = part.split(".")[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[0-9¹²³]", stem):
            raise ValueError("Windows device name is not a file target")
    return value


RelativePath = Annotated[str, AfterValidator(_relative_path)]


def _root(value: str) -> str:
    if value == "/" or re.fullmatch(r"[A-Z]:/", value):
        return value
    if re.match(r"^[A-Z]:/", value):
        _relative_path(value[3:])
    elif value.startswith("/") and not value.startswith("//"):
        _relative_path(value[1:])
    else:
        raise ValueError("root must be a normalized absolute POSIX or uppercase-drive path")
    return value


RepositoryRoot = Annotated[str, AfterValidator(_root)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


UtcTimestamp = Annotated[datetime, AfterValidator(_utc)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Contract(BaseModel):
    """Strict JSON records with validated copies and immutable nested collections."""

    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, validate_default=True,
        revalidate_instances="always", allow_inf_nan=False,
    )
    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_schema_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("only integer schema_version 1 is supported")
        return value

    def canonical_json(self) -> str:
        return canonical_json(self)

    def fingerprint(self) -> str:
        return fingerprint(self)

    def model_copy(self, *, update=None, deep=False):
        # Pydantic's default copy(update=...) skips validation. Do not allow that
        # shortcut to turn an otherwise valid contract into an invalid record.
        values = self.model_dump(mode="python")
        values.update(update or {})
        return type(self).model_validate(values)


def canonical_json(record: Contract) -> str:
    validated = type(record).model_validate(record)
    return json.dumps(
        validated.model_dump(mode="json"), sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )


def fingerprint(record: Contract) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


class RequestedOperation(Contract):
    action: OperationType
    target: RelativePath | None = None
    command_id: Identifier | None = None
    arguments: tuple[str, ...] = ()
    working_directory: str | None = None

    @model_validator(mode="after")
    def operation_shape(self):
        if self.action == "RUN_COMMAND":
            if self.target is not None or self.command_id is None or self.working_directory is None:
                raise ValueError("commands require command_id and working_directory, not target")
            if self.working_directory != ".":
                _relative_path(self.working_directory)
            # Arguments are exact argv tokens, not a shell string. G2 command
            # profiles must additionally constrain their semantics and effects.
            for arg in self.arguments:
                if not arg or any(ord(c) < 32 or ord(c) == 127 or c in ";|&`$<>" for c in arg):
                    raise ValueError("empty, control, or shell syntax in command argument")
        elif self.target is None or self.command_id is not None or self.arguments or self.working_directory is not None:
            raise ValueError("file operations require only a file target")
        return self


class TaskPacket(Contract):
    packet_id: Identifier
    project_id: Identifier
    task_id: Identifier
    milestone_id: Identifier
    repository_root: RepositoryRoot
    policy_id: Identifier
    policy_version: Annotated[int, Field(ge=1)]
    context_fingerprint: Fingerprint
    operations: Annotated[tuple[RequestedOperation, ...], Field(min_length=1)]
    created_at: UtcTimestamp = Field(default_factory=utc_now)

    @field_validator("operations")
    @classmethod
    def unique_operations(cls, value):
        if len({op.fingerprint() for op in value}) != len(value):
            raise ValueError("duplicate requested operation")
        return value


class OperationRule(Contract):
    """One exact operation and its policy classification; no globs or prefixes."""

    operation: RequestedOperation
    outcome: PermissionOutcome


class WorkspacePolicy(Contract):
    policy_id: Identifier
    policy_version: Annotated[int, Field(ge=1)]
    project_id: Identifier
    repository_root: RepositoryRoot
    rules: tuple[OperationRule, ...] = ()

    @field_validator("rules")
    @classmethod
    def unique_rules(cls, value):
        if len({rule.operation.fingerprint() for rule in value}) != len(value):
            raise ValueError("duplicate or conflicting operation rule")
        return value

    def classification(self, packet: TaskPacket) -> tuple[PermissionOutcome, tuple[str, ...]]:
        packet = TaskPacket.model_validate(packet)
        WorkspacePolicy.model_validate(self)
        if (packet.project_id, packet.repository_root, packet.policy_id, packet.policy_version) != (
            self.project_id, self.repository_root, self.policy_id, self.policy_version
        ):
            return "DENIED", ("POLICY_BINDING_MISMATCH",)
        rules = {rule.operation.fingerprint(): rule.outcome for rule in self.rules}
        outcomes = [rules.get(op.fingerprint(), "DENIED") for op in packet.operations]
        reasons = set()
        for op, outcome in zip(packet.operations, outcomes):
            if op.fingerprint() not in rules:
                reasons.add("UNLISTED_OPERATION")
            elif outcome == "DENIED":
                reasons.add("EXPLICIT_DENIAL")
            elif outcome == "HITL_REQUIRED":
                reasons.add("EXTERNAL_APPROVAL_REQUIRED")
        if "DENIED" in outcomes:
            outcome = "DENIED"
        elif "HITL_REQUIRED" in outcomes:
            outcome = "HITL_REQUIRED"
        else:
            outcome = "LOW_RISK"
            reasons.add("EXACT_RULE_MATCH")
        return outcome, tuple(sorted(reasons))

    def evaluate(self, packet: TaskPacket, *, decision_id: str, evaluated_at: datetime | None = None) -> PermissionDecision:
        outcome, reasons = self.classification(packet)
        return PermissionDecision(
            decision_id=decision_id, packet_fingerprint=packet.fingerprint(),
            policy_fingerprint=self.fingerprint(), outcome=outcome,
            reason_codes=reasons, evaluated_at=evaluated_at or utc_now(),
        )


class PermissionDecision(Contract):
    decision_id: Identifier
    packet_fingerprint: Fingerprint
    policy_fingerprint: Fingerprint
    outcome: PermissionOutcome
    reason_codes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    evaluated_at: UtcTimestamp = Field(default_factory=utc_now)

    def validate_binding(self, packet: TaskPacket, policy: WorkspacePolicy) -> None:
        PermissionDecision.model_validate(self)
        if self.packet_fingerprint != packet.fingerprint() or self.policy_fingerprint != policy.fingerprint():
            raise ValueError("stale or mismatched packet/policy fingerprint")
        if (self.outcome, self.reason_codes) != policy.classification(packet):
            raise ValueError("decision does not match exact policy evaluation")

    def permits_unattended_execution(self, packet: TaskPacket, policy: WorkspacePolicy) -> bool:
        self.validate_binding(packet, policy)
        return self.outcome == "LOW_RISK"


class EngineeringExecutionResult(Contract):
    execution_id: Identifier
    executor_id: Identifier
    project_id: Identifier
    task_id: Identifier
    packet_fingerprint: Fingerprint
    permission_decision_id: Identifier
    status: Literal["SUCCESS", "FAILED", "BLOCKED", "CANCELLED", "TIMEOUT"]
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    reported_files_created: tuple[RelativePath, ...] = ()
    reported_files_modified: tuple[RelativePath, ...] = ()
    reported_files_deleted: tuple[RelativePath, ...] = ()
    tests_executed: Annotated[int, Field(ge=0)] = 0
    tests_passed: Annotated[int, Field(ge=0)] = 0
    tests_failed: Annotated[int, Field(ge=0)] = 0
    tests_skipped: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def consistent_attempt(self):
        if self.finished_at < self.started_at:
            raise ValueError("execution finished before it started")
        if self.tests_executed != self.tests_passed + self.tests_failed + self.tests_skipped:
            raise ValueError("test counts must sum to executed count, including skips")
        if self.status == "SUCCESS" and self.tests_failed:
            raise ValueError("SUCCESS cannot report failed tests")
        changes = self.reported_files_created + self.reported_files_modified + self.reported_files_deleted
        # Windows paths are case-insensitive; conservatively prohibit aliases on
        # every host. Multiple lifecycle actions must be reduced to a net claim.
        if len({path.casefold() for path in changes}) != len(changes):
            raise ValueError("duplicate or contradictory net file-change claims")
        return self

    def validate_binding(self, packet: TaskPacket, decision: PermissionDecision, policy: WorkspacePolicy) -> None:
        EngineeringExecutionResult.model_validate(self)
        decision.validate_binding(packet, policy)
        if (self.project_id, self.task_id, self.packet_fingerprint, self.permission_decision_id) != (
            packet.project_id, packet.task_id, packet.fingerprint(), decision.decision_id
        ):
            raise ValueError("execution does not belong to packet/decision")
        if decision.outcome == "DENIED" and (
            self.status != "BLOCKED" or self.tests_executed or self.reported_files_created
            or self.reported_files_modified or self.reported_files_deleted
        ):
            raise ValueError("denied operation can only have a blocked, effect-free result")


class EvidenceRecord(Contract):
    evidence_id: Identifier
    project_id: Identifier
    task_id: Identifier
    execution_id: Identifier
    execution_fingerprint: Fingerprint
    check_id: Identifier
    producer_id: Identifier
    producer_kind: Literal["VERIFIER", "WORKER"]
    outcome: Literal["PASS", "FAIL", "BLOCKED"]
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    artifact_path: RelativePath | None = None
    artifact_sha256: Fingerprint | None = None
    observed_at: UtcTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def evidence_provenance(self):
        if (self.artifact_path is None) != (self.artifact_sha256 is None):
            raise ValueError("artifact reference and digest must be provided together")
        if self.outcome == "PASS" and (self.producer_kind != "VERIFIER" or self.artifact_path is None):
            raise ValueError("PASS requires verifier provenance and a hashed evidence artifact")
        return self

    def validate_binding(self, result: EngineeringExecutionResult) -> None:
        EvidenceRecord.model_validate(self)
        if (self.project_id, self.task_id, self.execution_id, self.execution_fingerprint) != (
            result.project_id, result.task_id, result.execution_id, result.fingerprint()
        ):
            raise ValueError("evidence does not belong to this execution result")
        if self.producer_kind == "VERIFIER" and self.producer_id == result.executor_id:
            raise ValueError("executor cannot attest as an independent verifier")
        if self.observed_at < result.finished_at:
            raise ValueError("post-execution evidence predates execution completion")
