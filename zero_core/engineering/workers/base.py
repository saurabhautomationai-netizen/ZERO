"""Core Worker Abstraction and Contracts for ZERO Engineering Organization.

Defines the universal EngineeringWorker interface, WorkerResult, WorkerStatus,
and ProjectContextPackage structures ensuring standardized execution across
native agents, agency specialists, ChatGPT, Antigravity, and future AI workers.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class WorkerStatus(str, enum.Enum):
    """Operational availability status of an engineering worker."""
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    MANUAL_TRANSPORT = "MANUAL_TRANSPORT"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class WorkerType(str, enum.Enum):
    """Execution tier of the worker."""
    NATIVE = "NATIVE"                  # In-process deterministic Python agent
    AGENCY = "AGENCY"                  # Agency-agents persona executed via LLM
    EXTERNAL_API = "EXTERNAL_API"      # Direct cloud REST API (e.g. OpenAI ChatGPT)
    EXTERNAL_LOCAL = "EXTERNAL_LOCAL"  # Local process/tool (e.g. Antigravity IDE/CLI)
    MANUAL = "MANUAL"                  # Human-assisted clipboard / prompt queue


class WorkerCapability(str, enum.Enum):
    """Distinct capabilities mapped to workers."""
    PRODUCT_REQUIREMENTS = "product_requirements"
    SRS = "srs"
    ARCHITECTURE = "architecture"
    ARCHITECTURE_REVIEW = "architecture_review"
    UI_DESIGN = "ui_design"
    UX_ARCHITECTURE = "ux_architecture"
    CODE_GENERATION = "code_generation"
    CODE_REFACTOR = "code_refactor"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    SECURITY_AUDIT = "security_audit"
    DATABASE = "database"
    DEVOPS = "devops"
    DEPLOYMENT = "deployment"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    PLANNING = "planning"


@dataclass
class ProjectContextPackage:
    """Task-specific, strictly sanitized context package delivered to a worker."""
    task_id: str
    project_id: str
    project_name: str
    current_phase: str
    task_title: str
    task_description: str
    acceptance_criteria: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    relevant_files: Dict[str, str] = field(default_factory=dict)  # rel_path -> content
    srs_excerpts: List[str] = field(default_factory=list)
    architecture_excerpts: List[str] = field(default_factory=list)
    prior_decisions: List[Dict[str, str]] = field(default_factory=list)
    previous_worker_output: Optional[str] = None
    sanitization_report: Optional[Dict[str, Any]] = None
    source_provenance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    security_level: str = "SENSITIVE_REDACTED"
    truncated_files: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerResult:
    """Standardized output produced by any engineering worker upon completing a task."""
    task_id: str
    worker_id: str
    status: str  # "SUCCESS" | "FAILED" | "BLOCKED" | "NEEDS_REVIEW" | "MANUAL_INPUT_REQUIRED"
    summary: str
    project_id: Optional[str] = None
    analysis: str = ""
    files_read: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    diff: str = ""
    commands_executed: List[str] = field(default_factory=list)
    tests_executed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    acceptance_criteria_results: Dict[str, bool] = field(default_factory=dict)
    artifacts_created: List[str] = field(default_factory=list)
    decisions: List[Dict[str, str]] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    blocked_by: Optional[str] = None
    requires_human: bool = False
    recommended_next_action: Optional[str] = None
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_success(self) -> bool:
        return self.status == "SUCCESS"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EngineeringWorker(ABC):
    """Universal base class for all workers in the ZERO Engineering Organization."""

    def __init__(
        self,
        worker_id: str,
        name: str,
        worker_type: WorkerType,
        capabilities: List[WorkerCapability],
        transport: str = "INTERNAL_CALL",
        risk_level: str = "LOW",
    ):
        self.worker_id = worker_id
        self.name = name
        self.worker_type = worker_type
        self.capabilities = capabilities
        self.transport = transport
        self.risk_level = risk_level
        self._status = WorkerStatus.AVAILABLE

    @property
    def status(self) -> WorkerStatus:
        return self._status

    def set_status(self, status: WorkerStatus) -> None:
        self._status = status

    def has_capability(self, capability: WorkerCapability | str) -> bool:
        cap_val = capability.value if isinstance(capability, WorkerCapability) else capability
        return any(
            (c.value if isinstance(c, WorkerCapability) else c) == cap_val
            for c in self.capabilities
        )

    @abstractmethod
    def run_task(
        self,
        context: ProjectContextPackage,
    ) -> WorkerResult:
        """Executes a discrete engineering task using the provided context package."""
        raise NotImplementedError

    def health_check(self) -> WorkerStatus:
        """Verifies transport connectivity and worker responsiveness."""
        return self._status
