"""Project Lifecycle Controller & Task DAG for ZERO Autonomous Engineering Organization.

Coordinates the complete end-to-end engineering journey:
Intake -> Discovery -> Scope (Gate 1) -> SRS -> Architecture -> Plan -> UI/UX (Gate 2) ->
Database -> Backend -> Agents -> Tools -> Frontend -> Integrations -> Testing ->
Security (Gate 4) -> Credentials (Gate 5) -> Release Candidate -> Deployment (Gate 8) -> Complete.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, TaskItem
from zero_core.engineering.validator import DEFAULT_PHASE_VALIDATOR, PhaseValidator

logger = logging.getLogger("zero.engineering.lifecycle")


class TaskState(str, enum.Enum):
    """Lifecycle states of a task in the TaskDAG."""
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    REVIEWING = "REVIEWING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    BLOCKED = "BLOCKED"
    WAITING_HITL = "WAITING_HITL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class DAGTaskNode:
    """Node in the task dependency DAG."""
    task_id: str
    phase: PhaseEnum
    title: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    state: TaskState = TaskState.PENDING
    target_files: List[str] = field(default_factory=list)
    assigned_worker: Optional[str] = None
    acceptance_criteria: List[str] = field(default_factory=list)
    result_summary: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase.value if isinstance(self.phase, PhaseEnum) else str(self.phase),
            "title": self.title,
            "description": self.description,
            "depends_on": self.depends_on,
            "state": self.state.value if isinstance(self.state, TaskState) else str(self.state),
            "target_files": self.target_files,
            "assigned_worker": self.assigned_worker,
            "acceptance_criteria": self.acceptance_criteria,
            "result_summary": self.result_summary,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class TaskDAG:
    """Dependency graph manager for engineering tasks with conflict detection."""

    def __init__(self):
        self.nodes: Dict[str, DAGTaskNode] = {}

    def add_task(
        self,
        task_id: str,
        phase: PhaseEnum,
        title: str,
        description: str,
        depends_on: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
    ) -> DAGTaskNode:
        node = DAGTaskNode(
            task_id=task_id,
            phase=phase,
            title=title,
            description=description,
            depends_on=depends_on or [],
            target_files=target_files or [],
            acceptance_criteria=acceptance_criteria or [],
        )
        self.nodes[task_id] = node
        return node

    def get_task(self, task_id: str) -> Optional[DAGTaskNode]:
        return self.nodes.get(task_id)

    def list_all_tasks(self) -> List[DAGTaskNode]:
        """Returns all registered task nodes in the DAG."""
        return list(self.nodes.values())

    def mark_completed(self, task_id: str, summary: str = "Completed successfully") -> None:
        if task_id in self.nodes:
            node = self.nodes[task_id]
            node.state = TaskState.COMPLETED
            node.result_summary = summary
            node.completed_at = datetime.now(timezone.utc).isoformat()

    def get_ready_tasks(self) -> List[DAGTaskNode]:
        """Returns all tasks whose dependencies are 100% completed."""
        ready = []
        for node in self.nodes.values():
            if node.state in (TaskState.PENDING, TaskState.READY):
                deps_met = all(
                    self.nodes[dep].state == TaskState.COMPLETED
                    for dep in node.depends_on
                    if dep in self.nodes
                )
                if deps_met:
                    node.state = TaskState.READY
                    ready.append(node)
        return ready

    def detect_conflicts(self, tasks: List[DAGTaskNode]) -> List[str]:
        """Identifies file collisions among candidate parallel tasks."""
        conflicts = []
        claimed_files: Dict[str, str] = {}
        for t in tasks:
            for f in t.target_files:
                if f in claimed_files:
                    conflicts.append(f"Collision on file '{f}' between {claimed_files[f]} and {t.task_id}")
                else:
                    claimed_files[f] = t.task_id
        return conflicts

    def to_dict(self) -> Dict[str, Any]:
        return {tid: node.to_dict() for tid, node in self.nodes.items()}


class ProjectLifecycleController:
    """Controls the progression of a project through its defined engineering phases."""

    # Logical progression sequence
    PHASE_SEQUENCE: List[PhaseEnum] = [
        PhaseEnum.PHASE_0_INTAKE,
        PhaseEnum.PHASE_1_DISCOVERY,
        PhaseEnum.PHASE_2_SRS,
        PhaseEnum.PHASE_3_ARCHITECTURE,
        PhaseEnum.PHASE_4_STRUCTURE,
        PhaseEnum.PHASE_5_UIUX,
        PhaseEnum.PHASE_6_PLANNING,
        PhaseEnum.PHASE_7_DATABASE,
        PhaseEnum.PHASE_8_AGENTS,
        PhaseEnum.PHASE_9_TOOLS,
        PhaseEnum.PHASE_10_BACKEND,
        PhaseEnum.PHASE_11_FRONTEND,
        PhaseEnum.PHASE_12_AI_LOGIC,
        PhaseEnum.PHASE_13_TESTING,
        PhaseEnum.PHASE_14_SECURITY,
        PhaseEnum.PHASE_15_CREDENTIALS,
        PhaseEnum.PHASE_16_INTEGRATIONS,
        PhaseEnum.PHASE_17_DEPLOYMENT,
        PhaseEnum.PHASE_18_DOCUMENTATION,
        PhaseEnum.PHASE_19_VERIFICATION,
        PhaseEnum.COMPLETED,
    ]

    # Required HITL Gates mapped to phases
    MANDATORY_GATES = {
        PhaseEnum.PHASE_1_DISCOVERY: "GATE_1_FEATURE_SCOPE",
        PhaseEnum.PHASE_5_UIUX: "GATE_2_UI_UX_DESIGN",
        PhaseEnum.PHASE_14_SECURITY: "GATE_4_SECURITY_PERMISSIONS",
        PhaseEnum.PHASE_15_CREDENTIALS: "GATE_5_CREDENTIALS",
        PhaseEnum.PHASE_17_DEPLOYMENT: "GATE_8_PRODUCTION_DEPLOYMENT",
    }

    def __init__(self, validator: Optional[PhaseValidator] = None):
        self.validator = validator or DEFAULT_PHASE_VALIDATOR
        self.dags: Dict[str, TaskDAG] = {}  # project_id -> TaskDAG

    def get_or_create_dag(self, manifest: ProjectManifest) -> TaskDAG:
        if manifest.project_id not in self.dags:
            dag = TaskDAG()
            # Populate default task DAG from manifest milestones if present
            for m in manifest.milestones:
                for t in m.tasks:
                    dag.add_task(
                        task_id=t.task_id,
                        phase=manifest.current_phase,
                        title=t.title,
                        description=t.description,
                        target_files=t.modified_files,
                        acceptance_criteria=t.acceptance_criteria,
                    )
                    if t.completed_at:
                        dag.mark_completed(t.task_id, "Imported completed milestone task")
            self.dags[manifest.project_id] = dag
        return self.dags[manifest.project_id]

    def check_phase_entry(self, manifest: ProjectManifest, phase: PhaseEnum) -> tuple[bool, List[str]]:
        """Verifies prerequisites before a project is allowed to enter a phase."""
        reasons = []

        if phase in (PhaseEnum.PHASE_2_SRS, PhaseEnum.PHASE_3_ARCHITECTURE):
            if manifest.scope_approval is None and manifest.current_phase == PhaseEnum.PHASE_1_DISCOVERY:
                reasons.append("Requires GATE 1 (Feature Scope) human approval.")

        elif phase in (PhaseEnum.PHASE_7_DATABASE, PhaseEnum.PHASE_10_BACKEND, PhaseEnum.PHASE_11_FRONTEND):
            if manifest.uiux_approval is None and manifest.project_type != "CLI_TOOL":
                reasons.append("Requires GATE 2 (UI/UX Design) human approval.")

        elif phase == PhaseEnum.PHASE_17_DEPLOYMENT:
            if manifest.security_status != "COMPLETED":
                reasons.append("Security audit and GATE 4 approval must be satisfied before deployment.")

        elif phase == PhaseEnum.COMPLETED:
            if manifest.deployment_status != "COMPLETED" and manifest.deployment_status != "SKIPPED":
                reasons.append("Production deployment verification (GATE 8) or explicit skip required to complete project.")
            if manifest.testing_status != "COMPLETED":
                reasons.append("Automated test verification required before project completion.")

        return len(reasons) == 0, reasons

    def check_phase_exit(self, manifest: ProjectManifest, phase: PhaseEnum) -> tuple[bool, List[str]]:
        """Verifies deliverables and gates before a project exits a phase."""
        reasons = []
        dag = self.get_or_create_dag(manifest)

        # Check for uncompleted tasks in this phase
        phase_tasks = [n for n in dag.nodes.values() if n.phase == phase]
        unfinished = [n.task_id for n in phase_tasks if n.state != TaskState.COMPLETED]
        if unfinished:
            reasons.append(f"Phase {phase.value} has {len(unfinished)} unfinished task(s): {', '.join(unfinished[:3])}")

        # Check mandatory HITL gate
        if phase in self.MANDATORY_GATES:
            gate_name = self.MANDATORY_GATES[phase]
            if gate_name == "GATE_1_FEATURE_SCOPE" and manifest.scope_approval is None:
                reasons.append("GATE 1 (Feature Scope) pending human decision.")
            elif gate_name == "GATE_2_UI_UX_DESIGN" and manifest.uiux_approval is None:
                reasons.append("GATE 2 (UI/UX Design) pending human decision.")
            elif gate_name == "GATE_4_SECURITY_PERMISSIONS" and manifest.security_status != "COMPLETED":
                reasons.append("GATE 4 (Security / Permissions) pending human approval.")
            elif gate_name == "GATE_8_PRODUCTION_DEPLOYMENT" and manifest.deployment_status != "COMPLETED":
                reasons.append("GATE 8 (Production Deployment) pending human authorization.")

        return len(reasons) == 0, reasons

    def get_next_phase(self, current_phase: PhaseEnum) -> Optional[PhaseEnum]:
        """Returns the next logical phase in sequence."""
        try:
            idx = self.PHASE_SEQUENCE.index(current_phase)
            if idx + 1 < len(self.PHASE_SEQUENCE):
                return self.PHASE_SEQUENCE[idx + 1]
        except ValueError:
            pass
        return None

    def calculate_progress_percentage(self, manifest: ProjectManifest) -> int:
        """Calculates project progress percentage across phases and tasks."""
        if manifest.current_phase == PhaseEnum.COMPLETED:
            return 100

        total_phases = len(self.PHASE_SEQUENCE) - 1
        try:
            curr_idx = self.PHASE_SEQUENCE.index(manifest.current_phase)
        except ValueError:
            curr_idx = 0

        phase_pct = int((curr_idx / total_phases) * 100)
        return min(max(phase_pct, 5), 95)


# Global singleton instance
DEFAULT_LIFECYCLE_CONTROLLER = ProjectLifecycleController()


# ---------------------------------------------------------------------------
# Authoritative Lifecycle State Snapshot
# ---------------------------------------------------------------------------

@dataclass
class AuthoritativeLifecycleState:
    """Single authoritative snapshot of a project's control-plane lifecycle state."""
    project_id: str
    project_name: str
    project_status: str
    current_phase: str
    scope_gate_status: str  # "APPROVED", "PENDING", "REJECTED"
    current_milestone: Optional[str]
    completed_milestones: List[str]
    pending_milestones: List[str]
    active_milestone: Optional[str]
    pending_user_actions: List[str]
    next_allowed_action: str
    is_m1_completed: bool
    is_m2_started: bool
    is_gate_1_approved: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_authoritative_lifecycle_state(
    project_id: str,
    manifest: Optional[ProjectManifest] = None,
    store: Optional[Any] = None,
) -> AuthoritativeLifecycleState:
    """Computes single authoritative lifecycle state for a project."""
    from zero_core.engineering.store import DEFAULT_PROJECT_STORE
    from zero_core.engineering.milestone_runner import (
        DEFAULT_MILESTONE_ENGINE,
        get_canonical_milestones_for_project,
    )

    p_store = store or DEFAULT_PROJECT_STORE
    p_manifest = manifest or p_store.get_project(project_id)
    if not p_manifest:
        raise ValueError(f"Project '{project_id}' not found in manifest store.")

    # 1. Scope Gate Status
    is_gate_1 = DEFAULT_MILESTONE_ENGINE.is_gate_approved(p_manifest, "GATE_1_FEATURE_SCOPE")
    scope_gate_status = "APPROVED" if is_gate_1 else "PENDING"

    # 2. Canonical milestones and completion analysis
    canonical_defs = get_canonical_milestones_for_project(p_manifest)
    canonical_order = ["M1_FOUNDATION", "M2_WORKFLOW_REFACTOR", "M3_AGENT_RAG", "M4_DASHBOARD_RELEASE"]

    completed_milestones: List[str] = []

    # Check explicit manifest milestone items
    for m in p_manifest.milestones:
        m_id = m.milestone_id
        if m.is_completed or getattr(m, "status", "") == "COMPLETED":
            if m_id not in completed_milestones:
                completed_milestones.append(m_id)
        elif m.tasks and all(t.status == "COMPLETED" or getattr(t, "status", "") == "COMPLETED" for t in m.tasks):
            if m_id not in completed_milestones:
                completed_milestones.append(m_id)

    # Check task-level completion for M1
    if "M1_FOUNDATION" not in completed_milestones:
        m1_task_ids = {"TASK-M1-01", "TASK-M1-02", "TASK-M1-03", "TASK-M1-04"}
        completed_task_set = set(p_manifest.completed_tasks or [])
        if m1_task_ids.issubset(completed_task_set):
            completed_milestones.append("M1_FOUNDATION")

    is_m1_completed = "M1_FOUNDATION" in completed_milestones

    # Check M2 started
    is_m2_started = False
    for m in p_manifest.milestones:
        if m.milestone_id == "M2_WORKFLOW_REFACTOR":
            if any(t.status in ("IN_PROGRESS", "COMPLETED") for t in m.tasks):
                is_m2_started = True

    # Compute pending milestones
    pending_milestones = [m for m in canonical_order if m not in completed_milestones]

    # Current milestone resolution
    if is_m1_completed and not is_m2_started:
        curr_milestone = "M2_WORKFLOW_REFACTOR"
    elif p_manifest.current_milestone and p_manifest.current_milestone not in completed_milestones:
        curr_milestone = p_manifest.current_milestone
    elif pending_milestones:
        curr_milestone = pending_milestones[0]
    else:
        curr_milestone = None

    # Next allowed action
    if not is_gate_1:
        next_action = "APPROVE_GATE_1 (Feature Scope Approval)"
    elif not is_m1_completed:
        next_action = "@Loop Engineering Agent execute milestone M1_FOUNDATION"
    elif is_m1_completed and not is_m2_started:
        next_action = "M2 PREFLIGHT / M2 HITL PROGRESSION ('@Loop Engineering Agent execute milestone M2_WORKFLOW_REFACTOR')"
    else:
        next_action = f"@Loop Engineering Agent execute milestone {curr_milestone}" if curr_milestone else "PROJECT_COMPLETED"

    status_val = p_manifest.project_status.value if hasattr(p_manifest.project_status, "value") else str(p_manifest.project_status)
    phase_val = p_manifest.current_phase.value if hasattr(p_manifest.current_phase, "value") else str(p_manifest.current_phase)

    return AuthoritativeLifecycleState(
        project_id=p_manifest.project_id,
        project_name=p_manifest.project_name,
        project_status=status_val,
        current_phase=phase_val,
        scope_gate_status=scope_gate_status,
        current_milestone=curr_milestone,
        completed_milestones=completed_milestones,
        pending_milestones=pending_milestones,
        active_milestone=curr_milestone,
        pending_user_actions=list(p_manifest.pending_user_actions or []),
        next_allowed_action=next_action,
        is_m1_completed=is_m1_completed,
        is_m2_started=is_m2_started,
        is_gate_1_approved=is_gate_1,
    )
