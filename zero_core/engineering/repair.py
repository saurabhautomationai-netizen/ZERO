"""Autonomous Repair Loop for ZERO Autonomous Engineering Organization.

Handles bounded automated repair cycles when code reviews or objective validations fail.
Packages failure evidence, reviewer findings, and correction plans, enforcing maximum attempt limits
and human escalation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zero_core.engineering.context_builder import DEFAULT_CONTEXT_BUILDER, ProjectContextBuilder
from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.reviewer import ReviewResult, ReviewVerdict
from zero_core.engineering.validator import ValidationResult, ValidationStatus
from zero_core.engineering.workers.base import WorkerResult
from zero_core.engineering.workers.registry import DEFAULT_WORKER_REGISTRY, WorkerRegistry

logger = logging.getLogger("zero.engineering.repair")

MAX_REPAIR_ATTEMPTS = 3


@dataclass
class RepairTask:
    """Encapsulates a corrective engineering task with diagnostic evidence."""
    repair_id: str
    original_task_id: str
    original_worker_id: str
    attempt_number: int
    failure_evidence: str
    review_findings: List[str] = field(default_factory=list)
    validation_findings: List[str] = field(default_factory=list)
    correction_plan: List[str] = field(default_factory=list)
    repair_constraints: List[str] = field(default_factory=list)
    diff: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_task_item(self) -> TaskItem:
        """Converts the repair package into a dispatchable TaskItem."""
        description = (
            f"REPAIR ATTEMPT #{self.attempt_number} for task '{self.original_task_id}'.\n\n"
            f"### Failure Evidence:\n{self.failure_evidence}\n\n"
            f"### Reviewer Findings:\n" + "\n".join(f"- {f}" for f in self.review_findings) + "\n\n"
            f"### Validation Failures:\n" + "\n".join(f"- {v}" for v in self.validation_findings) + "\n\n"
            f"### Actionable Correction Plan:\n" + "\n".join(f"- {c}" for c in self.correction_plan)
        )
        return TaskItem(
            task_id=self.repair_id,
            milestone_id="M_REPAIR",
            title=f"Repair: Resolve defects for {self.original_task_id} (Attempt #{self.attempt_number})",
            description=description,
            acceptance_criteria=[
                "Syntax validation passes with 0 errors",
                "Pytest suite executes cleanly with 0 failures",
                "Reviewer findings addressed",
            ],
            constraints=self.repair_constraints or ["Do not expand scope beyond reported defects"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RepairLoop:
    """Manages bounded autonomous repair cycles across failing tasks."""

    def __init__(
        self,
        worker_registry: Optional[WorkerRegistry] = None,
        context_builder: Optional[ProjectContextBuilder] = None,
        max_attempts: int = MAX_REPAIR_ATTEMPTS,
    ):
        self.worker_registry = worker_registry or DEFAULT_WORKER_REGISTRY
        self.context_builder = context_builder or DEFAULT_CONTEXT_BUILDER
        self.max_attempts = max_attempts
        self.repair_attempts: Dict[str, int] = {}  # task_id -> count

    def get_attempt_count(self, task_id: str) -> int:
        return self.repair_attempts.get(task_id, 0)

    def should_repair(
        self,
        task_id: str,
        review_result: Optional[ReviewResult] = None,
        validation_result: Optional[ValidationResult] = None,
    ) -> bool:
        """Determines if a task requires and is eligible for automated repair."""
        needs_review_fix = review_result is not None and not review_result.is_pass
        needs_val_fix = validation_result is not None and not validation_result.is_pass

        if not (needs_review_fix or needs_val_fix):
            return False

        attempts = self.get_attempt_count(task_id)
        return attempts < self.max_attempts

    def create_repair_task(
        self,
        original_task: TaskItem,
        original_worker_id: str,
        review_result: Optional[ReviewResult] = None,
        validation_result: Optional[ValidationResult] = None,
        diff: str = "",
    ) -> Optional[RepairTask]:
        """Creates a diagnostic repair task or returns None if max attempts are exceeded."""
        task_id = original_task.task_id
        current_attempts = self.repair_attempts.get(task_id, 0)
        if current_attempts >= self.max_attempts:
            logger.warning(
                "Task '%s' reached max repair attempts (%d). Escalating to HITL.",
                task_id, self.max_attempts,
            )
            return None

        self.repair_attempts[task_id] = current_attempts + 1
        attempt_num = self.repair_attempts[task_id]

        # Extract review findings & correction plan
        review_findings = [f.description for f in review_result.findings] if review_result else []
        correction_plan = list(review_result.recommended_corrections) if review_result else []

        # Extract validation failures
        validation_findings = list(validation_result.checks_failed) if validation_result else []
        failure_evidence = validation_result.failure_summary if validation_result else (review_result.summary if review_result else "Verification failed.")

        return RepairTask(
            repair_id=f"rep_{task_id[:8]}_{attempt_num}_{uuid.uuid4().hex[:4]}",
            original_task_id=task_id,
            original_worker_id=original_worker_id,
            attempt_number=attempt_num,
            failure_evidence=failure_evidence,
            review_findings=review_findings,
            validation_findings=validation_findings,
            correction_plan=correction_plan or ["Fix syntax errors", "Ensure tests pass"],
            repair_constraints=[
                "Do NOT expand scope beyond fixing reported defects",
                "Preserve working architecture and existing tests",
            ],
            diff=diff,
        )

    def select_repair_worker(
        self,
        original_worker_id: str,
        review_result: Optional[ReviewResult] = None,
        validation_result: Optional[ValidationResult] = None,
    ) -> str:
        """Selects the best worker to execute the repair task."""
        from zero_core.engineering.workers.base import WorkerStatus

        # For multi-file code failures or when Antigravity was the implementer, Antigravity repairs
        if original_worker_id == "worker_antigravity":
            ag = self.worker_registry.get("worker_antigravity")
            if ag and ag.health_check() == WorkerStatus.AVAILABLE:
                return "worker_antigravity"
            return "worker_coding_agent"

        # If original worker is available and registered, use it for repair
        orig = self.worker_registry.get(original_worker_id)
        if orig and orig.health_check() == WorkerStatus.AVAILABLE:
            return original_worker_id

        # Default to CodingAgent for in-process code/test repairs
        return "worker_coding_agent"

    def execute_repair(
        self,
        manifest: ProjectManifest,
        repair_task: RepairTask,
        repair_worker_id: str,
    ) -> WorkerResult:
        """Dispatches the repair task to the selected worker with full sanitization."""
        logger.info(
            "RepairLoop: Dispatching repair '%s' (attempt %d) to %s",
            repair_task.repair_id, repair_task.attempt_number, repair_worker_id,
        )
        worker = self.worker_registry.get(repair_worker_id)
        if not worker:
            raise ValueError(f"Repair worker '{repair_worker_id}' is not registered.")

        task_item = repair_task.to_task_item()
        context = self.context_builder.build_context(
            project=manifest,
            task=task_item,
            worker=worker,
        )

        result = worker.run_task(context)

        # Record repair event in manifest
        manifest.repair_history.append({
            "repair_id": repair_task.repair_id,
            "original_task_id": repair_task.original_task_id,
            "attempt_number": repair_task.attempt_number,
            "repair_worker_id": repair_worker_id,
            "status": result.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        manifest.repair_attempt_count = repair_task.attempt_number

        return result


# Global singleton instance
DEFAULT_REPAIR_LOOP = RepairLoop()
