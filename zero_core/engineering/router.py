"""Intelligent Task Router for ZERO Autonomous Engineering Organization.

Analyzes engineering tasks, classifies requirements, assesses worker health and transport
availability, and deterministically selects the optimal department and worker with full
explainability and fallback support.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zero_core.engineering.departments.registry import DEFAULT_DEPARTMENT_REGISTRY, DepartmentRegistry
from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.workers.base import (
    WorkerCapability,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.registry import DEFAULT_WORKER_REGISTRY, WorkerRegistry, WorkerSpec

logger = logging.getLogger("zero.engineering.router")


class EngineeringTaskType(str, enum.Enum):
    """Categorization of engineering activities."""
    DISCOVERY = "DISCOVERY"
    PRODUCT_REQUIREMENTS = "PRODUCT_REQUIREMENTS"
    SRS = "SRS"
    ARCHITECTURE = "ARCHITECTURE"
    ADR = "ADR"
    DATABASE_DESIGN = "DATABASE_DESIGN"
    API_DESIGN = "API_DESIGN"
    AGENT_DESIGN = "AGENT_DESIGN"
    UIUX = "UIUX"
    FRONTEND = "FRONTEND"
    BACKEND = "BACKEND"
    DATABASE_IMPLEMENTATION = "DATABASE_IMPLEMENTATION"
    CODE_GENERATION = "CODE_GENERATION"
    CODE_REFACTOR = "CODE_REFACTOR"
    BUG_FIX = "BUG_FIX"
    TESTING = "TESTING"
    CODE_REVIEW = "CODE_REVIEW"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    RESEARCH = "RESEARCH"
    DOCUMENTATION = "DOCUMENTATION"
    DEVOPS = "DEVOPS"
    DEPLOYMENT = "DEPLOYMENT"
    REPAIR = "REPAIR"


@dataclass
class RoutingDecision:
    """Structured, fully explainable routing decision."""
    task_id: str
    task_type: EngineeringTaskType
    department: str
    selected_worker: str
    alternative_workers: List[str] = field(default_factory=list)
    selection_score: float = 1.0
    selection_reasons: List[str] = field(default_factory=list)
    worker_health: str = "AVAILABLE"
    transport: str = "INTERNAL_CALL"
    risk_level: str = "LOW"
    requires_approval: bool = False
    fallback_worker: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskRouter:
    """Intelligent, policy-driven Task Router for ZERO Engineering."""

    def __init__(
        self,
        worker_registry: Optional[WorkerRegistry] = None,
        department_registry: Optional[DepartmentRegistry] = None,
    ):
        self.worker_registry = worker_registry or DEFAULT_WORKER_REGISTRY
        self.department_registry = department_registry or DEFAULT_DEPARTMENT_REGISTRY
        self.performance_history: Dict[str, Dict[str, Any]] = {}

    def classify_task(self, title: str, description: str = "") -> EngineeringTaskType:
        """Classifies a task into a standard EngineeringTaskType based on domain keywords."""
        import re
        corpus = f"{title} {description}".lower()
        words = set(re.findall(r"\b[a-z0-9_]+\b", corpus))

        if any(k in corpus for k in ("review architecture", "critique architecture", "architectural review")):
            return EngineeringTaskType.ARCHITECTURE_REVIEW
        if any(k in corpus for k in ("code review", "pr review", "diff review", "review pull request")):
            return EngineeringTaskType.CODE_REVIEW
        if any(k in corpus for k in ("security audit", "vulnerability", "credential check", "cve")):
            return EngineeringTaskType.SECURITY_REVIEW
        if words.intersection({"ui", "ux", "prototype", "wireframe", "theme"}) or "design system" in corpus:
            return EngineeringTaskType.UIUX
        if words.intersection({"srs"}) or "functional requirements" in corpus or "software requirements" in corpus:
            return EngineeringTaskType.SRS
        if words.intersection({"adr"}) or any(k in corpus for k in ("architecture", "system blueprint")):
            return EngineeringTaskType.ARCHITECTURE
        if "database design" in corpus or "db schema" in corpus or words.intersection({"erd"}):
            return EngineeringTaskType.DATABASE_DESIGN
        if "api design" in corpus or "rest api spec" in corpus or words.intersection({"openapi"}):
            return EngineeringTaskType.API_DESIGN
        if any(k in corpus for k in ("agent architecture", "agent design", "multi-agent")):
            return EngineeringTaskType.AGENT_DESIGN
        if words.intersection({"test", "tests", "pytest", "e2e"}) or "unit test" in corpus:
            return EngineeringTaskType.TESTING
        if words.intersection({"refactor"}) or "clean up" in corpus or "restructure code" in corpus:
            return EngineeringTaskType.CODE_REFACTOR
        if words.intersection({"bug", "patch"}) or "fix error" in corpus or "repair failure" in corpus:
            return EngineeringTaskType.BUG_FIX
        if words.intersection({"research", "benchmark", "benchmarking"}) or "competitive analysis" in corpus:
            return EngineeringTaskType.RESEARCH
        if words.intersection({"doc", "docs", "readme", "guide"}):
            return EngineeringTaskType.DOCUMENTATION
        if words.intersection({"deploy", "deployment", "docker", "release"}):
            return EngineeringTaskType.DEPLOYMENT

        return EngineeringTaskType.CODE_GENERATION

    def route_task(
        self,
        task: TaskItem,
        project: Optional[ProjectManifest] = None,
    ) -> RoutingDecision:
        """Determines the optimal worker and department for an engineering task."""
        logger.info("TaskRouter routing task '%s' (%s)", task.title, task.task_id)

        task_type = self.classify_task(task.title, task.description)

        # 1. Map to Department
        dept_spec = self.department_registry.find_for_task(f"{task.title} {task.description}")
        department_id = dept_spec.department_id if dept_spec else "engineering"

        # 2. Worker Selection Mapping
        primary_worker_id = None
        fallback_worker_id = None
        reasons = []

        if task_type in (EngineeringTaskType.SRS, EngineeringTaskType.PRODUCT_REQUIREMENTS, EngineeringTaskType.ARCHITECTURE, EngineeringTaskType.ADR):
            primary_worker_id = "worker_project_builder"
            fallback_worker_id = "worker_chatgpt"
            reasons.append("ProjectBuilderWorker specializes in deterministic inception, SRS, and ADR formulation.")

        elif task_type in (EngineeringTaskType.ARCHITECTURE_REVIEW, EngineeringTaskType.CODE_REVIEW):
            primary_worker_id = "worker_chatgpt"
            fallback_worker_id = "worker_coding_agent"
            reasons.append("ChatGPTWorker specializes in architectural critique, code review, and quality assessment.")

        elif task_type == EngineeringTaskType.UIUX:
            primary_worker_id = "worker_uiux_designer"
            fallback_worker_id = "worker_chatgpt"
            reasons.append("UIUXDepartmentCoordinator manages design systems, page inventories, and interactive prototypes.")

        elif task_type in (EngineeringTaskType.CODE_GENERATION, EngineeringTaskType.CODE_REFACTOR, EngineeringTaskType.BUG_FIX):
            # Prefer Antigravity for multi-file repo edits if available, else CodingAgent
            ag_worker = self.worker_registry.get("worker_antigravity")
            if ag_worker and ag_worker.health_check() == WorkerStatus.AVAILABLE:
                primary_worker_id = "worker_antigravity"
                fallback_worker_id = "worker_coding_agent"
                reasons.append("AntigravityWorker selected for repository-wide multi-file implementation.")
            else:
                primary_worker_id = "worker_coding_agent"
                fallback_worker_id = "worker_antigravity"
                reasons.append("CodingAgentWorker selected for deterministic in-process AST code generation.")

        elif task_type == EngineeringTaskType.TESTING:
            primary_worker_id = "worker_coding_agent"
            fallback_worker_id = "worker_antigravity"
            reasons.append("CodingAgentWorker manages local pytest test suite execution and AST verification.")

        elif task_type == EngineeringTaskType.RESEARCH:
            primary_worker_id = "worker_research_agent"
            fallback_worker_id = "worker_chatgpt"
            reasons.append("ResearchWorker specializes in multi-source technical intelligence.")

        else:
            primary_worker_id = "worker_coding_agent"
            fallback_worker_id = "worker_project_builder"
            reasons.append("Default engineering worker selected.")

        # 3. Health & Availability Check
        selected_worker_obj = self.worker_registry.get(primary_worker_id)
        worker_health = selected_worker_obj.health_check() if selected_worker_obj else WorkerStatus.UNAVAILABLE

        # If primary worker is not healthy/configured, route to fallback
        final_worker_id = primary_worker_id
        if worker_health in (WorkerStatus.NOT_CONFIGURED, WorkerStatus.UNAVAILABLE, WorkerStatus.FAILED):
            if fallback_worker_id:
                fallback_obj = self.worker_registry.get(fallback_worker_id)
                fallback_health = fallback_obj.health_check() if fallback_obj else WorkerStatus.UNAVAILABLE
                if fallback_health == WorkerStatus.AVAILABLE:
                    reasons.append(f"Primary worker {primary_worker_id} status is {worker_health.value}; fell back to {fallback_worker_id}.")
                    final_worker_id = fallback_worker_id
                    selected_worker_obj = fallback_obj
                    worker_health = fallback_health
                else:
                    reasons.append(f"Both primary and fallback workers require configuration. Falling back to MANUAL_TRANSPORT.")
            else:
                reasons.append(f"Worker {primary_worker_id} not available. Fallback to MANUAL_TRANSPORT.")

        transport = getattr(selected_worker_obj, "transport", "INTERNAL_CALL")
        risk_level = getattr(selected_worker_obj, "risk_level", "LOW")

        return RoutingDecision(
            task_id=task.task_id,
            task_type=task_type,
            department=department_id,
            selected_worker=final_worker_id,
            alternative_workers=[w for w in (primary_worker_id, fallback_worker_id) if w and w != final_worker_id],
            selection_score=1.0,
            selection_reasons=reasons,
            worker_health=worker_health.value,
            transport=transport,
            risk_level=risk_level,
            requires_approval=risk_level == "HIGH",
            fallback_worker=fallback_worker_id,
        )

    def record_performance(self, worker_id: str, task_type: str, success: bool, execution_seconds: float = 0.0) -> None:
        """Collects lightweight execution metrics for future routing optimization."""
        if worker_id not in self.performance_history:
            self.performance_history[worker_id] = {
                "tasks_attempted": 0,
                "tasks_passed": 0,
                "failures": 0,
                "total_duration": 0.0,
            }

        rec = self.performance_history[worker_id]
        rec["tasks_attempted"] += 1
        if success:
            rec["tasks_passed"] += 1
        else:
            rec["failures"] += 1
        rec["total_duration"] += execution_seconds


# Global singleton instance
DEFAULT_TASK_ROUTER = TaskRouter()
