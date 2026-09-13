"""G6A's inert, fake-port-only controlled orchestration boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import PureWindowsPath
from typing import Any, Protocol
import hashlib


MAX_TEXT = 240


class OrchestrationError(ValueError):
    """A fixed-code, fail-closed orchestration error."""


class State(str, Enum):
    QUEUED = "QUEUED"; LEASED = "LEASED"; POLICY_CHECKED = "POLICY_CHECKED"
    EXECUTION_REPORTED = "EXECUTION_REPORTED"; VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED = "VERIFIED"; REVIEW_PENDING = "REVIEW_PENDING"; REVIEWED = "REVIEWED"
    COMPLETED = "COMPLETED"; BLOCKED = "BLOCKED"; FAILED = "FAILED"
    CANCELLED = "CANCELLED"; REQUIRES_REVERIFICATION = "REQUIRES_REVERIFICATION"


TERMINAL = frozenset({State.COMPLETED, State.BLOCKED, State.FAILED, State.CANCELLED})
TRANSITIONS = {
    State.QUEUED: frozenset({State.LEASED, State.CANCELLED}),
    State.LEASED: frozenset({State.POLICY_CHECKED, State.BLOCKED, State.CANCELLED,
                             State.REQUIRES_REVERIFICATION}),
    State.POLICY_CHECKED: frozenset({State.EXECUTION_REPORTED, State.BLOCKED, State.CANCELLED,
                                     State.REQUIRES_REVERIFICATION, State.FAILED}),
    State.EXECUTION_REPORTED: frozenset({State.VERIFICATION_PENDING, State.REQUIRES_REVERIFICATION,
                                         State.FAILED, State.CANCELLED}),
    State.VERIFICATION_PENDING: frozenset({State.VERIFIED, State.BLOCKED, State.FAILED,
                                           State.CANCELLED, State.REQUIRES_REVERIFICATION}),
    State.REQUIRES_REVERIFICATION: frozenset({State.VERIFICATION_PENDING, State.BLOCKED,
                                               State.CANCELLED}),
    State.VERIFIED: frozenset({State.REVIEW_PENDING, State.BLOCKED, State.CANCELLED,
                               State.REQUIRES_REVERIFICATION}),
    State.REVIEW_PENDING: frozenset({State.REVIEWED, State.BLOCKED, State.FAILED, State.CANCELLED,
                                     State.REQUIRES_REVERIFICATION}),
    State.REVIEWED: frozenset({State.COMPLETED, State.BLOCKED, State.CANCELLED,
                               State.REQUIRES_REVERIFICATION}),
}


class G1Outcome(str, Enum): LOW_RISK = "LOW_RISK"; DENIED = "DENIED"; HITL_REQUIRED = "HITL_REQUIRED"
class G2Outcome(str, Enum): SUCCESS = "SUCCESS"; FAILED = "FAILED"; BLOCKED = "BLOCKED"; UNCERTAIN = "UNCERTAIN"
class G3Outcome(str, Enum): PASS = "PASS"; FAILED = "FAILED"; BLOCKED = "BLOCKED"; INCONCLUSIVE = "INCONCLUSIVE"
class G4Outcome(str, Enum): VERIFIED = "VERIFIED"; CORRUPT = "CORRUPT"; REQUIRES_REVERIFICATION = "REQUIRES_REVERIFICATION"
class G5Outcome(str, Enum): APPROVED = "APPROVED"; REJECTED = "REJECTED"; REMEDIATION = "REMEDIATION"; BLOCKED = "BLOCKED"
class PlanningDisposition(str, Enum):
    READY_FOR_CONTROLLED_EXECUTION = "READY_FOR_CONTROLLED_EXECUTION"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    LEASE_INVALID = "LEASE_INVALID"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


def _text(value: str, name: str, limit: int = MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > limit or any(ord(char) < 32 for char in value):
        raise OrchestrationError(f"INVALID_{name}")
    return value


def _utc(value: datetime, name: str = "TIME") -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OrchestrationError(f"INVALID_{name}")
    return value


def _count(value: int, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum: raise OrchestrationError(f"INVALID_{name}")
    return value


@dataclass(frozen=True)
class ServiceBindings:
    g1: "G1Port"; g2: "G2Port"; g3: "G3Port"; g4: "G4Port"; g5: "G5Port"


@dataclass(frozen=True)
class TrustedConfiguration:
    project_id: str; repository_root: str; max_queue_depth: int; max_active_leases: int
    lease_duration: timedelta; max_attempts: int; max_steps: int; max_wall_clock: timedelta
    max_executions: int; max_verifications: int; max_reviews: int; backoff: tuple[timedelta, ...]
    permitted_operation_classes: frozenset[str]; cancellation_policy: str; services: ServiceBindings
    max_lease_renewals: int = 1
    def __post_init__(self) -> None:
        _text(self.project_id, "PROJECT"); _text(self.cancellation_policy, "CANCELLATION_POLICY")
        root = str(PureWindowsPath(self.repository_root))
        if not PureWindowsPath(root).is_absolute() or root != self.repository_root or not self.repository_root.startswith("F:\\"):
            raise OrchestrationError("INVALID_ROOT")
        for value, name, minimum in ((self.max_queue_depth,"QUEUE",1),(self.max_active_leases,"LEASES",1),
                                     (self.max_attempts,"ATTEMPTS",1),(self.max_steps,"STEPS",1),
                                     (self.max_executions,"EXECUTIONS",0),(self.max_verifications,"VERIFICATIONS",0),
                                     (self.max_reviews,"REVIEWS",0)):
            _count(value, name, minimum)
        _count(self.max_lease_renewals, "LEASE_RENEWALS")
        if self.lease_duration <= timedelta() or self.max_wall_clock <= timedelta() or not self.backoff:
            raise OrchestrationError("INVALID_LIMIT")
        if any(type(item) is not timedelta or item < timedelta() for item in self.backoff): raise OrchestrationError("INVALID_BACKOFF")
        if not self.permitted_operation_classes or any(type(item) is not str for item in self.permitted_operation_classes): raise OrchestrationError("INVALID_OPERATIONS")


@dataclass(frozen=True)
class OrchestrationTask:
    task_id: str; idempotency_key: str; project_id: str; repository_root: str; operation_class: str
    packet: Any; policy: Any; decision: Any; content_digest: str
    def __post_init__(self) -> None:
        for value, name in ((self.task_id,"TASK"),(self.idempotency_key,"IDEMPOTENCY"),(self.project_id,"PROJECT"),
                            (self.repository_root,"ROOT"),(self.operation_class,"OPERATION"),(self.content_digest,"DIGEST")):_text(value,name)
        if self.packet is None or self.policy is None or self.decision is None: raise OrchestrationError("MISSING_G1")


@dataclass(frozen=True)
class BudgetLedger:
    started_at: datetime; steps: int = 0; attempts: int = 0; executions: int = 0; verifications: int = 0; reviews: int = 0
    def __post_init__(self) -> None:
        _utc(self.started_at)
        for value, name in ((self.steps,"STEPS"),(self.attempts,"ATTEMPTS"),(self.executions,"EXECUTIONS"),(self.verifications,"VERIFICATIONS"),(self.reviews,"REVIEWS")):_count(value,name)


@dataclass(frozen=True)
class Lease:
    task_id: str; lease_id: str; owner_id: str; expires_at: datetime; renewals: int = 0
    def __post_init__(self) -> None:
        _text(self.task_id,"TASK"); _text(self.lease_id,"LEASE"); _text(self.owner_id,"OWNER"); _utc(self.expires_at); _count(self.renewals,"RENEWALS")


@dataclass(frozen=True)
class QueueEntry:
    task: OrchestrationTask; state: State; sequence: int; ledger: BudgetLedger; lease: Lease | None = None
    def __post_init__(self) -> None: _count(self.sequence,"SEQUENCE",1)


@dataclass(frozen=True)
class Attempt:
    task_id: str; number: int; kind: str; retry_safe: bool; summary: str
    def __post_init__(self) -> None: _text(self.task_id,"TASK"); _count(self.number,"ATTEMPT",1); _text(self.kind,"KIND"); _text(self.summary,"SUMMARY")


@dataclass(frozen=True)
class CancellationRequest:
    task_id: str; requested_at: datetime; reason_code: str
    def __post_init__(self) -> None: _text(self.task_id,"TASK"); _utc(self.requested_at); _text(self.reason_code,"REASON")


@dataclass(frozen=True)
class TransitionEvent:
    task_id: str; from_state: State; to_state: State; at: datetime; reason_code: str
    def __post_init__(self) -> None: _text(self.task_id,"TASK"); _utc(self.at); _text(self.reason_code,"REASON")


@dataclass(frozen=True)
class OrchestrationResult:
    task_id: str; state: State; summary: str; ledger: BudgetLedger; uncertainty: bool = False
    def __post_init__(self) -> None: _text(self.task_id,"TASK"); _text(self.summary,"SUMMARY")


@dataclass(frozen=True)
class RemainingBudget:
    steps: int; attempts: int; executions: int; verifications: int; reviews: int
    def __post_init__(self) -> None:
        for value, name in ((self.steps,"STEPS"),(self.attempts,"ATTEMPTS"),(self.executions,"EXECUTIONS"),(self.verifications,"VERIFICATIONS"),(self.reviews,"REVIEWS")):
            _count(value, name)


@dataclass(frozen=True)
class OrchestrationPlan:
    """A descriptive result only; its booleans intentionally cannot authorize work."""
    disposition: PlanningDisposition; task_fingerprint: str; lease_fingerprint: str
    configuration_fingerprint: str; current_state: State; required_gates: tuple[str, ...]
    remaining_budget: RemainingBudget; reason_code: str; authoritative: bool = False
    permits_execution: bool = False; permits_completion: bool = False
    def __post_init__(self) -> None:
        if type(self.disposition) is not PlanningDisposition or type(self.current_state) is not State:
            raise OrchestrationError("INVALID_PLAN")
        for value, name in ((self.task_fingerprint,"TASK_FINGERPRINT"),(self.lease_fingerprint,"LEASE_FINGERPRINT"),(self.configuration_fingerprint,"CONFIGURATION_FINGERPRINT"),(self.reason_code,"PLAN_REASON")):
            _text(value, name)
        if type(self.required_gates) is not tuple or self.required_gates != ("G1", "G2", "G3", "G4", "G5", "G4_FINAL"):
            raise OrchestrationError("INVALID_PLAN")
        if type(self.remaining_budget) is not RemainingBudget or self.authoritative is not False or self.permits_execution is not False or self.permits_completion is not False:
            raise OrchestrationError("INVALID_PLAN")


class QueueRepository(Protocol):
    def enqueue(self, task: OrchestrationTask, ledger: BudgetLedger, maximum: int) -> QueueEntry: ...
    def claim(self, owner_id: str, now: datetime, duration: timedelta, maximum: int) -> QueueEntry | None: ...
    def compare_and_swap(self, entry: QueueEntry, lease: Lease, state: State, ledger: BudgetLedger, reason: str) -> QueueEntry: ...
    def find_idempotency(self, key: str) -> QueueEntry | None: ...
    def recover_expired(self, now: datetime) -> int: ...
    def renew(self, entry: QueueEntry, lease: Lease, now: datetime, duration: timedelta, maximum: int) -> Lease: ...
    def read_claimed(self, task_id: str, expected_version: int) -> QueueEntry | None: ...

class G1Port(Protocol):
    def validate(self, task: OrchestrationTask, config: TrustedConfiguration) -> G1Outcome: ...
class G2Port(Protocol):
    def execute(self, task: OrchestrationTask, attempt: int) -> G2Outcome: ...
class G3Port(Protocol):
    def verify(self, task: OrchestrationTask) -> G3Outcome: ...
class G4Port(Protocol):
    def checkpoint(self, task: OrchestrationTask, state: State) -> G4Outcome: ...
class G5Port(Protocol):
    def review(self, task: OrchestrationTask) -> G5Outcome: ...
class Clock(Protocol):
    def now(self) -> datetime: ...
class IdentifierSource(Protocol):
    def next_id(self) -> str: ...
class CancellationObserver(Protocol):
    def requested(self, task_id: str) -> CancellationRequest | None: ...


class Coordinator:
    """One bounded call chain; it owns no worker, provider or persistent store."""
    def __init__(self, config: TrustedConfiguration, queue: QueueRepository, clock: Clock, ids: IdentifierSource, cancellations: CancellationObserver):
        self.config, self.queue, self.clock, self.ids, self.cancellations = config, queue, clock, ids, cancellations

    def submit(self, task: OrchestrationTask) -> QueueEntry:
        self._bound(task)
        old = self.queue.find_idempotency(task.idempotency_key)
        if old is not None:
            if old.task.content_digest != task.content_digest: raise OrchestrationError("IDEMPOTENCY_CONFLICT")
            return old
        return self.queue.enqueue(task, BudgetLedger(self.clock.now()), self.config.max_queue_depth)

    def run_once(self, owner_id: str) -> OrchestrationResult | None:
        now = self.clock.now(); _utc(now); entry = self.queue.claim(_text(owner_id,"OWNER"), now, self.config.lease_duration, self.config.max_active_leases)
        if entry is None: return None
        if entry.lease is None: raise OrchestrationError("CLAIM_INVALID")
        return self._run(entry)

    def renew_lease(self, entry: QueueEntry) -> Lease:
        """Renew the exact live lease once within the configured bounded policy."""
        if entry.lease is None or entry.state in TERMINAL:
            raise OrchestrationError("LEASE_NOT_LIVE")
        return self.queue.renew(entry, entry.lease, self.clock.now(), self.config.lease_duration,
                                self.config.max_lease_renewals)

    def plan_claimed(self, task: OrchestrationTask, lease: Lease, expected_version: int) -> OrchestrationPlan:
        """Read-only, repeatable G6B planning surface for an already-owned lease.

        This method neither calls a gate nor changes queue or durable state.  A
        repository without the explicit read-only ownership operation is blocked.
        """
        task_id = task.task_id if isinstance(task, OrchestrationTask) else "UNKNOWN"
        if isinstance(task, OrchestrationTask) and self._cancelled(task):
            return self._plan(PlanningDisposition.CANCELLED, task, lease, State.LEASED, "CANCELLED")
        try:
            task.__post_init__()
            lease.__post_init__()
            _count(expected_version, "EXPECTED_VERSION", 1)
            self._bound(task)
        except (AttributeError, OrchestrationError):
            return self._blocked_plan(task_id, "INVALID_BINDING")
        reader = getattr(self.queue, "read_claimed", None)
        if not callable(reader):
            return self._plan(PlanningDisposition.BLOCKED, task, lease, State.LEASED, "OWNERSHIP_UNAVAILABLE")
        entry = reader(task.task_id, expected_version)
        if not isinstance(entry, QueueEntry):
            return self._plan(PlanningDisposition.BLOCKED, task, lease, State.LEASED, "OWNERSHIP_MISSING")
        try:
            entry.__post_init__()
            if entry.task is not task or entry.lease != lease or entry.sequence != expected_version or entry.state is not State.LEASED:
                return self._plan(PlanningDisposition.LEASE_INVALID, task, lease, entry.state, "LEASE_MISMATCH")
            now = self.clock.now(); _utc(now)
            if lease.task_id != task.task_id or lease.expires_at <= now:
                return self._plan(PlanningDisposition.LEASE_INVALID, task, lease, entry.state, "LEASE_EXPIRED")
            budget = self._remaining_for_plan(entry.ledger, now)
        except OrchestrationError as error:
            return self._plan(PlanningDisposition.BUDGET_EXHAUSTED if str(error) == "BUDGET_EXHAUSTED" else PlanningDisposition.BLOCKED, task, lease, entry.state, str(error))
        return OrchestrationPlan(PlanningDisposition.READY_FOR_CONTROLLED_EXECUTION, task.content_digest,
                                 self._lease_fingerprint(lease), self._configuration_fingerprint(), entry.state,
                                 ("G1", "G2", "G3", "G4", "G5", "G4_FINAL"), budget, "PLAN_ONLY")

    def _remaining_for_plan(self, ledger: BudgetLedger, now: datetime) -> RemainingBudget:
        if now - ledger.started_at > self.config.max_wall_clock:
            raise OrchestrationError("BUDGET_EXHAUSTED")
        # A full pipeline needs four charged steps, one attempt/execution,
        # one verification and one review.  Planning never charges any of them.
        needed = (("steps", 4, self.config.max_steps), ("attempts", 1, self.config.max_attempts),
                  ("executions", 1, self.config.max_executions), ("verifications", 1, self.config.max_verifications),
                  ("reviews", 1, self.config.max_reviews))
        if any(getattr(ledger, name) + amount > maximum for name, amount, maximum in needed):
            raise OrchestrationError("BUDGET_EXHAUSTED")
        return RemainingBudget(self.config.max_steps - ledger.steps, self.config.max_attempts - ledger.attempts,
                               self.config.max_executions - ledger.executions, self.config.max_verifications - ledger.verifications,
                               self.config.max_reviews - ledger.reviews)

    def _plan(self, disposition: PlanningDisposition, task: OrchestrationTask, lease: Lease, state: State, reason: str) -> OrchestrationPlan:
        return OrchestrationPlan(disposition, task.content_digest, self._lease_fingerprint(lease), self._configuration_fingerprint(), state,
                                 ("G1", "G2", "G3", "G4", "G5", "G4_FINAL"), RemainingBudget(0,0,0,0,0), reason)

    def _blocked_plan(self, task_id: str, reason: str) -> OrchestrationPlan:
        safe = task_id if type(task_id) is str and task_id else "UNKNOWN"
        return OrchestrationPlan(PlanningDisposition.BLOCKED, safe, "UNAVAILABLE", self._configuration_fingerprint(), State.LEASED,
                                 ("G1", "G2", "G3", "G4", "G5", "G4_FINAL"), RemainingBudget(0,0,0,0,0), reason)

    @staticmethod
    def _lease_fingerprint(lease: Lease) -> str:
        return hashlib.sha256((lease.task_id + "|" + lease.lease_id + "|" + lease.owner_id + "|" + lease.expires_at.isoformat() + "|" + str(lease.renewals)).encode("utf-8")).hexdigest()

    def _configuration_fingerprint(self) -> str:
        c = self.config
        value = "|".join((c.project_id,c.repository_root,",".join(sorted(c.permitted_operation_classes)),str(c.max_steps),str(c.max_attempts),str(c.max_executions),str(c.max_verifications),str(c.max_reviews),str(c.max_wall_clock.total_seconds())))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _run(self, entry: QueueEntry) -> OrchestrationResult:
        task, lease, ledger = entry.task, entry.lease, entry.ledger
        assert lease is not None
        if self._cancelled(task): return self._finish(entry, lease, State.CANCELLED, ledger, "CANCELLED", False)
        try: self._bound(task)
        except OrchestrationError: return self._finish(entry, lease, State.BLOCKED, ledger, "TRUST_BINDING", False)
        ledger = self._charge(ledger, "steps")
        decision = self.config.services.g1.validate(task, self.config)
        if decision is not G1Outcome.LOW_RISK: return self._finish(entry, lease, State.BLOCKED, ledger, "G1_BLOCKED", False)
        entry = self._move(entry, lease, State.POLICY_CHECKED, ledger, "G1_VALID")
        if self._cancelled(task): return self._finish(entry, lease, State.CANCELLED, ledger, "CANCELLED", False)
        ledger = self._charge(entry.ledger, "steps", "attempts", "executions")
        execution = self.config.services.g2.execute(task, ledger.attempts)
        if execution is not G2Outcome.SUCCESS:
            return self._finish(entry, lease, State.REQUIRES_REVERIFICATION if execution is G2Outcome.UNCERTAIN else State.FAILED, ledger, "G2_NOT_SUCCESS", execution is G2Outcome.UNCERTAIN)
        entry = self._move(entry, lease, State.EXECUTION_REPORTED, ledger, "G2_REPORTED")
        if self._cancelled(task): return self._finish(entry, lease, State.REQUIRES_REVERIFICATION, ledger, "CANCELLED_AFTER_EXECUTION", True)
        entry = self._move(entry, lease, State.VERIFICATION_PENDING, ledger, "G3_REQUIRED")
        ledger = self._charge(entry.ledger, "steps", "verifications")
        verification = self.config.services.g3.verify(task)
        if verification is not G3Outcome.PASS: return self._finish(entry, lease, State.BLOCKED, ledger, "G3_NOT_PASS", False)
        entry = self._move(entry, lease, State.VERIFIED, ledger, "G3_PASS")
        if self.config.services.g4.checkpoint(task, State.VERIFIED) is not G4Outcome.VERIFIED:
            return self._finish(entry, lease, State.REQUIRES_REVERIFICATION, ledger, "G4_NOT_VERIFIED", True)
        if self._cancelled(task): return self._finish(entry, lease, State.CANCELLED, ledger, "CANCELLED", False)
        entry = self._move(entry, lease, State.REVIEW_PENDING, ledger, "G5_REQUIRED")
        ledger = self._charge(entry.ledger, "steps", "reviews")
        review = self.config.services.g5.review(task)
        if review is not G5Outcome.APPROVED: return self._finish(entry, lease, State.BLOCKED, ledger, "G5_NOT_APPROVED", False)
        entry = self._move(entry, lease, State.REVIEWED, ledger, "G5_ADVISORY_APPROVAL")
        if self._cancelled(task): return self._finish(entry, lease, State.CANCELLED, entry.ledger, "CANCELLED", False)
        if self.config.services.g4.checkpoint(task, State.REVIEWED) is not G4Outcome.VERIFIED:
            return self._finish(entry, lease, State.REQUIRES_REVERIFICATION, ledger, "G4_COMPLETION_BINDING", True)
        return self._finish(entry, lease, State.COMPLETED, entry.ledger, "ALL_GATES_BOUND", False)

    def _bound(self, task: OrchestrationTask) -> None:
        if task.project_id != self.config.project_id or task.repository_root != self.config.repository_root or task.operation_class not in self.config.permitted_operation_classes: raise OrchestrationError("TRUST_BINDING")
    def _cancelled(self, task: OrchestrationTask) -> bool: return self.cancellations.requested(task.task_id) is not None
    def _charge(self, ledger: BudgetLedger, *fields: str) -> BudgetLedger:
        now = self.clock.now()
        if now - ledger.started_at > self.config.max_wall_clock: raise OrchestrationError("BUDGET_TIME")
        values = {name: getattr(ledger, name) + (1 if name in fields else 0) for name in ("steps","attempts","executions","verifications","reviews")}
        limits = {"steps":self.config.max_steps,"attempts":self.config.max_attempts,"executions":self.config.max_executions,"verifications":self.config.max_verifications,"reviews":self.config.max_reviews}
        if any(values[name] > limits[name] for name in fields): raise OrchestrationError("BUDGET_EXHAUSTED")
        return BudgetLedger(ledger.started_at, **values)
    def _move(self, entry: QueueEntry, lease: Lease, state: State, ledger: BudgetLedger, reason: str) -> QueueEntry:
        if state not in TRANSITIONS.get(entry.state, frozenset()): raise OrchestrationError("ILLEGAL_TRANSITION")
        return self.queue.compare_and_swap(entry, lease, state, ledger, reason)
    def _finish(self, entry: QueueEntry, lease: Lease, state: State, ledger: BudgetLedger, reason: str, uncertainty: bool) -> OrchestrationResult:
        saved = self._move(entry, lease, state, ledger, reason)
        return OrchestrationResult(saved.task.task_id, saved.state, reason, saved.ledger, uncertainty)
