"""Reviewer Engine for ZERO Autonomous Engineering Organization.

Enforces independent, rigorous peer review of engineering artifacts, code changes,
and architectural specifications before objective validation and task completion.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zero_core.engineering.context_builder import DEFAULT_CONTEXT_BUILDER, ProjectContextBuilder
from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
)
from zero_core.engineering.workers.external import ChatGPTWorker
from zero_core.engineering.workers.registry import DEFAULT_WORKER_REGISTRY, WorkerRegistry

logger = logging.getLogger("zero.engineering.reviewer")


class ReviewVerdict(str, enum.Enum):
    """Outcomes of an engineering review."""
    PASS = "PASS"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    BLOCKED = "BLOCKED"
    ESCALATE = "ESCALATE"


@dataclass
class ReviewFinding:
    """A granular finding identified during review."""
    category: str  # "ARCHITECTURE" | "CODE_QUALITY" | "SECURITY" | "TESTING" | "UIUX"
    severity: str  # "LOW" | "MEDIUM" | "HIGH"
    description: str
    recommendation: str
    blocking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    """Standardized outcome of an independent engineering review."""
    task_id: str
    reviewer_id: str
    subject_worker_id: str
    verdict: ReviewVerdict
    score: int
    summary: str
    findings: List[ReviewFinding] = field(default_factory=list)
    recommended_corrections: List[str] = field(default_factory=list)
    requires_human: bool = False
    confidence: float = 0.95
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_pass(self) -> bool:
        return self.verdict == ReviewVerdict.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "reviewer_id": self.reviewer_id,
            "subject_worker_id": self.subject_worker_id,
            "verdict": self.verdict.value if isinstance(self.verdict, ReviewVerdict) else str(self.verdict),
            "score": self.score,
            "summary": self.summary,
            "findings": [f.to_dict() if hasattr(f, "to_dict") else f for f in self.findings],
            "recommended_corrections": self.recommended_corrections,
            "requires_human": self.requires_human,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


class ReviewerEngine:
    """Orchestrates independent technical reviews across engineering tasks."""

    def __init__(
        self,
        worker_registry: Optional[WorkerRegistry] = None,
        context_builder: Optional[ProjectContextBuilder] = None,
    ):
        self.worker_registry = worker_registry or DEFAULT_WORKER_REGISTRY
        self.context_builder = context_builder or DEFAULT_CONTEXT_BUILDER

    def select_independent_reviewer(self, subject_worker_id: str) -> str:
        """Selects an independent reviewer, strictly preventing workers from reviewing their own work."""
        # ChatGPTWorker is the lead architect & reviewer for implementation / scaffolding workers
        if subject_worker_id in ("worker_antigravity", "worker_coding_agent", "worker_project_builder", "worker_uiux_designer"):
            return "worker_chatgpt"

        # If ChatGPT is the subject, Coding Agent or a QA specialist conducts the review
        if subject_worker_id == "worker_chatgpt":
            return "worker_coding_agent"

        return "worker_chatgpt"

    def review_task_execution(
        self,
        manifest: ProjectManifest,
        task: TaskItem,
        worker_result: WorkerResult,
        reviewer_id: Optional[str] = None,
    ) -> ReviewResult:
        """Executes an independent review of a worker's output."""
        subject_worker_id = worker_result.worker_id
        active_reviewer_id = reviewer_id or self.select_independent_reviewer(subject_worker_id)

        # Enforce reviewer independence
        if active_reviewer_id == subject_worker_id:
            raise ValueError(f"Reviewer Independence Violation: {active_reviewer_id} cannot review its own work.")

        logger.info(
            "ReviewerEngine: %s reviewing output of %s for task '%s'",
            active_reviewer_id, subject_worker_id, task.title,
        )

        reviewer_worker = self.worker_registry.get(active_reviewer_id)

        # If ChatGPTWorker is available, invoke its review method
        if isinstance(reviewer_worker, ChatGPTWorker):
            context = self.context_builder.build_context(
                project=manifest,
                task=task,
                worker=reviewer_worker,
            )
            chatgpt_res = reviewer_worker.review(
                context=context,
                diff=worker_result.diff,
                test_evidence=f"Tests executed: {worker_result.tests_executed}, Passed: {worker_result.tests_passed}",
            )

            meta = chatgpt_res.execution_metadata
            verdict_str = meta.get("verdict", "PASS").upper()
            score = meta.get("score", 90)
            correction_plan = meta.get("correction_plan", [])

            verdict = ReviewVerdict.PASS if verdict_str == "PASS" else ReviewVerdict.NEEDS_CORRECTION

            findings = [
                ReviewFinding(
                    category="CODE_QUALITY",
                    severity="HIGH" if verdict != ReviewVerdict.PASS else "LOW",
                    description=line.lstrip("- "),
                    recommendation="Apply corrective patch in repair loop",
                    blocking=verdict != ReviewVerdict.PASS,
                )
                for line in chatgpt_res.analysis.splitlines() if line.strip().startswith("-")
            ]

            return ReviewResult(
                task_id=task.task_id,
                reviewer_id=active_reviewer_id,
                subject_worker_id=subject_worker_id,
                verdict=verdict,
                score=score,
                summary=chatgpt_res.summary,
                findings=findings,
                recommended_corrections=correction_plan,
                requires_human=verdict == ReviewVerdict.BLOCKED,
            )

        # Fallback / Native review logic
        is_clean = len(worker_result.errors) == 0 and worker_result.is_success
        verdict = ReviewVerdict.PASS if is_clean else ReviewVerdict.NEEDS_CORRECTION
        score = 95 if is_clean else 60

        findings = [
            ReviewFinding(
                category="ENGINEERING",
                severity="HIGH" if not is_clean else "LOW",
                description=err,
                recommendation="Resolve error in repair loop",
                blocking=not is_clean,
            )
            for err in worker_result.errors
        ]

        return ReviewResult(
            task_id=task.task_id,
            reviewer_id=active_reviewer_id,
            subject_worker_id=subject_worker_id,
            verdict=verdict,
            score=score,
            summary=f"Independent review completed by {active_reviewer_id}: {verdict.value}",
            findings=findings,
            recommended_corrections=[f.recommendation for f in findings if f.blocking],
            requires_human=False,
        )


# Global singleton instance
DEFAULT_REVIEWER_ENGINE = ReviewerEngine()
