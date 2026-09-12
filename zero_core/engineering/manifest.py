"""Engineering Project Manifest & Data Models for ZERO Loop Engineering Agent.

Defines the complete persistent engineering state schema for tracking software projects
across their entire lifecycle: Discovery -> Architecture -> UI/UX -> Implementation -> Testing -> Security -> Deployment.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProjectStatus(str, enum.Enum):
    INTAKE = "INTAKE"
    DISCOVERY = "DISCOVERY"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class PhaseEnum(str, enum.Enum):
    PHASE_0_INTAKE = "PHASE_0_INTAKE"
    PHASE_1_DISCOVERY = "PHASE_1_DISCOVERY"
    PHASE_2_SRS = "PHASE_2_SRS"
    PHASE_3_ARCHITECTURE = "PHASE_3_ARCHITECTURE"
    PHASE_4_STRUCTURE = "PHASE_4_STRUCTURE"
    PHASE_5_UIUX = "PHASE_5_UIUX"
    PHASE_6_PLANNING = "PHASE_6_PLANNING"
    PHASE_7_DATABASE = "PHASE_7_DATABASE"
    PHASE_8_AGENTS = "PHASE_8_AGENTS"
    PHASE_9_TOOLS = "PHASE_9_TOOLS"
    PHASE_10_BACKEND = "PHASE_10_BACKEND"
    PHASE_11_FRONTEND = "PHASE_11_FRONTEND"
    PHASE_12_AI_LOGIC = "PHASE_12_AI_LOGIC"
    PHASE_13_TESTING = "PHASE_13_TESTING"
    PHASE_14_SECURITY = "PHASE_14_SECURITY"
    PHASE_15_CREDENTIALS = "PHASE_15_CREDENTIALS"
    PHASE_16_INTEGRATIONS = "PHASE_16_INTEGRATIONS"
    PHASE_17_DEPLOYMENT = "PHASE_17_DEPLOYMENT"
    PHASE_18_DOCUMENTATION = "PHASE_18_DOCUMENTATION"
    PHASE_19_VERIFICATION = "PHASE_19_VERIFICATION"
    COMPLETED = "COMPLETED"


class ApprovalGateType(str, enum.Enum):
    FEATURE_SCOPE = "FEATURE_SCOPE"
    UI_UX_DESIGN = "UI_UX_DESIGN"
    SECURITY_PERMISSIONS = "SECURITY_PERMISSIONS"
    CREDENTIALS_INTEGRATIONS = "CREDENTIALS_INTEGRATIONS"
    PRODUCTION_DEPLOYMENT = "PRODUCTION_DEPLOYMENT"
    CUSTOM = "CUSTOM"


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class TaskItem(BaseModel):
    task_id: str
    milestone_id: str
    title: str
    description: str
    assigned_agent: str = "native/project-builder"
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    created_files: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    test_commands: List[str] = Field(default_factory=list)
    required_artifacts: List[str] = Field(default_factory=list)
    required_symbols: List[str] = Field(default_factory=list)
    required_tests: List[str] = Field(default_factory=list)
    mutation_expected: bool = True
    failure_reason: Optional[str] = None
    retry_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


class MilestoneItem(BaseModel):
    milestone_id: str
    title: str
    phase: PhaseEnum
    description: str
    tasks: List[TaskItem] = Field(default_factory=list)
    is_completed: bool = False
    acceptance_tests: List[str] = Field(default_factory=list)


class Checkpoint(BaseModel):
    checkpoint_id: str
    project_id: str
    phase: PhaseEnum
    milestone: Optional[str] = None
    description: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    manifest_snapshot: Dict[str, Any]
    file_hashes: Dict[str, str] = Field(default_factory=dict)
    git_commit: Optional[str] = None


class ProjectManifest(BaseModel):
    """The master engineering project state manifest."""
    project_id: str
    project_name: str
    project_type: str = "NEW_PROJECT"  # "NEW_PROJECT" | "EXISTING_PROJECT"
    description: str
    repository_path: str
    repository_url: Optional[str] = None

    # Status & Progress
    project_status: ProjectStatus = ProjectStatus.INTAKE
    current_phase: PhaseEnum = PhaseEnum.PHASE_0_INTAKE
    current_milestone: Optional[str] = None
    current_task: Optional[str] = None
    overall_progress: int = Field(default=0, ge=0, le=100)

    # Feature Scope
    feature_scope: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "must_have": [],
            "should_have": [],
            "nice_to_have": [],
            "future": [],
        }
    )
    approved_features: List[str] = Field(default_factory=list)
    rejected_features: List[str] = Field(default_factory=list)
    pending_features: List[str] = Field(default_factory=list)
    subsystems: List[str] = Field(default_factory=list)

    # Granular Subsystem Status
    requirements_status: str = "PENDING"
    architecture_status: str = "PENDING"
    uiux_status: str = "PENDING"
    implementation_status: str = "PENDING"
    database_status: str = "PENDING"
    backend_status: str = "PENDING"
    frontend_status: str = "PENDING"
    agent_status: str = "PENDING"
    tool_status: str = "PENDING"
    integration_status: str = "PENDING"
    testing_status: str = "PENDING"
    security_status: str = "PENDING"
    credential_status: str = "PENDING"
    deployment_status: str = "PENDING"
    documentation_status: str = "PENDING"

    # Project Builder & UI/UX Department Tracking
    project_builder_status: str = "PENDING"
    project_builder_worker: Optional[str] = "worker_project_builder"
    project_builder_artifacts: List[str] = Field(default_factory=list)
    uiux_worker_assignments: Dict[str, str] = Field(default_factory=dict)
    uiux_artifacts: List[str] = Field(default_factory=list)
    uiux_review_status: str = "PENDING"
    uiux_revision_count: int = 0
    scope_approval: Optional[Any] = None
    uiux_approval: Optional[Dict[str, Any]] = None
    security_approval: Optional[Dict[str, Any]] = None
    deployment_approval: Optional[Dict[str, Any]] = None
    approved_design_version: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)

    # Phase 5: Autonomous Routing, Review, Validation & Repair Tracking
    routing_history: List[Dict[str, Any]] = Field(default_factory=list)
    worker_execution_history: List[Dict[str, Any]] = Field(default_factory=list)
    review_history: List[Dict[str, Any]] = Field(default_factory=list)
    validation_history: List[Dict[str, Any]] = Field(default_factory=list)
    repair_history: List[Dict[str, Any]] = Field(default_factory=list)
    repair_attempt_count: int = 0
    current_reviewer: Optional[str] = None
    last_validation: Optional[Dict[str, Any]] = None
    last_failure: Optional[Dict[str, Any]] = None
    last_successful_checkpoint: Optional[str] = None

    # History & Decision Logs
    approval_history: List[Dict[str, Any]] = Field(default_factory=list)
    decision_history: List[Dict[str, Any]] = Field(default_factory=list)
    architecture_decisions: List[Dict[str, str]] = Field(default_factory=list)
    uiux_decisions: List[Dict[str, str]] = Field(default_factory=list)
    technology_decisions: List[Dict[str, str]] = Field(default_factory=list)

    # Diagnostics & Resilience
    known_bugs: List[str] = Field(default_factory=list)
    technical_debt: List[str] = Field(default_factory=list)
    failed_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    retry_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Active State & Tasks
    active_agent: Optional[str] = None
    active_task: Optional[str] = None
    milestones: List[MilestoneItem] = Field(default_factory=list)
    task_dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    acceptance_criteria: Dict[str, List[str]] = Field(default_factory=dict)
    completed_tasks: List[str] = Field(default_factory=list)
    remaining_tasks: List[str] = Field(default_factory=list)
    blocked_tasks: List[str] = Field(default_factory=list)
    pending_user_actions: List[str] = Field(default_factory=list)

    # Checkpoint Metadata
    last_checkpoint: Optional[str] = None
    last_successful_phase: Optional[PhaseEnum] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completion_status: str = "IN_PROGRESS"

    def record_decision(self, category: str, decision: str, rationale: str) -> None:
        """Records an engineering decision."""
        entry = {
            "category": category,
            "decision": decision,
            "rationale": rationale,
            "phase": self.current_phase.value if isinstance(self.current_phase, PhaseEnum) else self.current_phase,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.decision_history.append(entry)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def record_approval(self, gate: str, approver: str, status: str, notes: str = "") -> None:
        """Records a human-in-the-loop approval decision."""
        entry = {
            "gate": gate,
            "approver": approver,
            "status": status,
            "notes": notes,
            "phase": self.current_phase.value if isinstance(self.current_phase, PhaseEnum) else self.current_phase,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.approval_history.append(entry)
        if any(k in gate.lower() for k in ("scope", "feature", "gate_1")):
            self.scope_approval = entry
        elif any(k in gate.lower() for k in ("ui", "design", "gate_2")):
            self.uiux_approval = entry
        elif any(k in gate.lower() for k in ("security", "gate_4")):
            self.security_approval = entry
        elif any(k in gate.lower() for k in ("deploy", "gate_8")):
            self.deployment_approval = entry
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def calculate_progress(self) -> int:
        """Computes accurate weighted progress based on phase completion and completed tasks."""
        phase_weights = {
            PhaseEnum.PHASE_0_INTAKE: 5,
            PhaseEnum.PHASE_1_DISCOVERY: 10,
            PhaseEnum.PHASE_2_SRS: 15,
            PhaseEnum.PHASE_3_ARCHITECTURE: 25,
            PhaseEnum.PHASE_4_STRUCTURE: 30,
            PhaseEnum.PHASE_5_UIUX: 40,
            PhaseEnum.PHASE_6_PLANNING: 45,
            PhaseEnum.PHASE_7_DATABASE: 55,
            PhaseEnum.PHASE_8_AGENTS: 60,
            PhaseEnum.PHASE_9_TOOLS: 65,
            PhaseEnum.PHASE_10_BACKEND: 75,
            PhaseEnum.PHASE_11_FRONTEND: 85,
            PhaseEnum.PHASE_12_AI_LOGIC: 90,
            PhaseEnum.PHASE_13_TESTING: 95,
            PhaseEnum.PHASE_14_SECURITY: 97,
            PhaseEnum.PHASE_17_DEPLOYMENT: 99,
            PhaseEnum.COMPLETED: 100,
        }
        base_progress = phase_weights.get(self.current_phase, 0)
        self.overall_progress = min(100, max(self.overall_progress, base_progress))
        return self.overall_progress
