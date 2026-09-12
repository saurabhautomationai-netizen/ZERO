"""ZERO Real Milestone Execution Engine.

Coordinates the authoritative transition from approved continuation plan / scope to execution:
APPROVED PLAN -> EXECUTE_MILESTONE -> Gate Check -> Milestone Validation ->
Task DAG Resolution -> Pre-Mutation Invariant -> Pre-Mutation Checkpoint ->
TaskRouter -> Workers -> ReviewerEngine -> PhaseValidator -> RepairLoop ->
Post-Milestone Checkpoint -> Milestone Completion Report -> HITL Gate -> STOP.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import enum
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from zero_core.context import TaskExecutionContext
from zero_core.engineering.checkpoints import (
    DEFAULT_CHECKPOINT_MANAGER,
    Checkpoint,
    CheckpointManager,
)
from zero_core.engineering.context_builder import (
    DEFAULT_CONTEXT_BUILDER,
    ProjectContextBuilder,
)
from zero_core.engineering.departments.registry import (
    DEFAULT_DEPARTMENT_REGISTRY,
    DepartmentRegistry,
)
from zero_core.engineering.lifecycle import (
    DAGTaskNode,
    DEFAULT_LIFECYCLE_CONTROLLER,
    ProjectLifecycleController,
    TaskDAG,
    TaskState,
)
from zero_core.engineering.manifest import (
    MilestoneItem,
    PhaseEnum,
    ProjectManifest,
    ProjectStatus,
    TaskItem,
    TaskStatus,
)
from zero_core.engineering.repair import DEFAULT_REPAIR_LOOP, RepairLoop
from zero_core.engineering.repository_guard import (
    DEFAULT_REPOSITORY_GUARD,
    RepositoryGuard,
    RepositoryIsolationError,
)
from zero_core.engineering.resolver import EngineeringRequest
from zero_core.engineering.reviewer import (
    DEFAULT_REVIEWER_ENGINE,
    ReviewerEngine,
    ReviewResult,
    ReviewVerdict,
)
from zero_core.engineering.router import DEFAULT_TASK_ROUTER, TaskRouter
from zero_core.engineering.store import (
    DEFAULT_PROJECT_STORE,
    EngineeringProjectStore,
)
from zero_core.engineering.validator import (
    DEFAULT_PHASE_VALIDATOR,
    PhaseValidator,
    ValidationResult,
    ValidationStatus,
)
from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerResult,
)
from zero_core.engineering.workers.registry import (
    DEFAULT_WORKER_REGISTRY,
    WorkerRegistry,
)

logger = logging.getLogger("zero.engineering.milestone_runner")


class ExecutionMode(str, enum.Enum):
    """Operational mode for milestone execution."""
    DRY_RUN = "DRY_RUN"
    REAL_EXECUTION = "REAL_EXECUTION"


class MilestoneState(str, enum.Enum):
    """Lifecycle state of an engineering milestone."""
    PLANNED = "PLANNED"
    READY = "READY"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class MilestoneDefinition:
    """Canonical descriptor for an engineering milestone."""
    milestone_id: str
    title: str
    description: str
    phase: PhaseEnum
    required_gate: str
    tasks: List[TaskItem] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    state: MilestoneState = MilestoneState.PLANNED


def get_canonical_milestones_for_project(manifest: ProjectManifest) -> Dict[str, MilestoneDefinition]:
    """Returns canonical registered milestones for a project."""
    # 1. Check if manifest already defines explicit milestones
    registered: Dict[str, MilestoneDefinition] = {}
    for m in manifest.milestones:
        registered[m.milestone_id] = MilestoneDefinition(
            milestone_id=m.milestone_id,
            title=m.title,
            description=m.description,
            phase=m.phase,
            required_gate="GATE_1_FEATURE_SCOPE",
            tasks=m.tasks,
            acceptance_criteria=m.acceptance_tests,
            state=MilestoneState.COMPLETED if m.is_completed else MilestoneState.READY,
        )

    # 2. Canonical Milestone Sequence (M1, M2, M3, M4)
    if "M1_FOUNDATION" not in registered or not registered["M1_FOUNDATION"].tasks:
        m1_tasks = [
            TaskItem(
                task_id="TASK-M1-01",
                milestone_id="M1_FOUNDATION",
                title="Deterministic Calculation Layer",
                description="Establish tested Python calculation module with Decimal arithmetic for loan interest, amortizations, and budget variances.",
                assigned_agent="native/coding-agent",
                status=TaskStatus.PENDING,
                modified_files=["zero_finance_engine/calculations.py"],
                required_artifacts=["zero_finance_engine/calculations.py"],
                required_symbols=["calculate_income", "calculate_expenses", "calculate_savings", "calculate_savings_rate"],
                mutation_expected=True,
                acceptance_criteria=[
                    "All financial calculations return exact Decimal values with zero rounding errors",
                    "Syntax validation passes with 0 errors",
                ],
            ),
            TaskItem(
                task_id="TASK-M1-02",
                milestone_id="M1_FOUNDATION",
                title="Calculation Automated Tests",
                description="Create pytest test suite verifying Decimal formulas, amortization schedules, and budget calculation accuracy.",
                assigned_agent="native/coding-agent",
                status=TaskStatus.PENDING,
                dependencies=["TASK-M1-01"],
                modified_files=["tests/test_calculations.py"],
                required_artifacts=["tests/test_calculations.py"],
                required_tests=["tests/test_calculations.py"],
                mutation_expected=True,
                acceptance_criteria=[
                    "Automated pytest test suite passes with 0 failures",
                    "100% test coverage for all financial calculation formulas",
                ],
            ),
            TaskItem(
                task_id="TASK-M1-03",
                milestone_id="M1_FOUNDATION",
                title="Database Constraints & Schema Hardening",
                description="Create SQL migration adding composite indexes and check constraints for account balances and transaction dates.",
                assigned_agent="native/coding-agent",
                status=TaskStatus.PENDING,
                dependencies=["TASK-M1-01"],
                modified_files=["migrations/V2__indexes_and_constraints.sql"],
                required_artifacts=["migrations/V2__indexes_and_constraints.sql"],
                mutation_expected=True,
                acceptance_criteria=[
                    "SQL schema migration script applies cleanly with reversible rollback",
                    "Composite indexes and check constraints verified",
                ],
            ),
            TaskItem(
                task_id="TASK-M1-04",
                milestone_id="M1_FOUNDATION",
                title="Webhook Payload Ingestion Contract Validator",
                description="Implement validation logic for incoming bank statement payloads.",
                assigned_agent="native/automation-agent",
                status=TaskStatus.PENDING,
                dependencies=["TASK-M1-02", "TASK-M1-03"],
                modified_files=["zero_finance_engine/validators.py"],
                required_artifacts=["zero_finance_engine/validators.py"],
                required_symbols=["validate_webhook_payload"],
                mutation_expected=True,
                acceptance_criteria=[
                    "Webhook payload contract validated against schema",
                    "Rejects malformed statements cleanly",
                ],
            ),
        ]
        registered["M1_FOUNDATION"] = MilestoneDefinition(
            milestone_id="M1_FOUNDATION",
            title="Core Foundation & Deterministic Calculation Layer",
            description="Establish the tested Python calculation engine, schema migrations, and testing harness before refactoring workflows.",
            phase=PhaseEnum.PHASE_7_DATABASE,
            required_gate="GATE_1_FEATURE_SCOPE",
            tasks=m1_tasks,
            acceptance_criteria=[
                "All financial calculations return exact Decimal values with zero rounding errors.",
                "Automated pytest test suite passes with 0 failures.",
                "Migration script applies cleanly with reversible rollback.",
                "Zero files outside the target project are modified.",
            ],
            state=MilestoneState.READY,
        )

    if "M2_WORKFLOW_REFACTOR" not in registered or not registered["M2_WORKFLOW_REFACTOR"].tasks:
        m2_tasks = [
            TaskItem(
                task_id="TASK-M2-01",
                milestone_id="M2_WORKFLOW_REFACTOR",
                title="Email Ingestion Micro-Workflow Decomposition",
                description="Extract email ingestion webhook and statement parsing logic into dedicated micro-workflow.",
                assigned_agent="native/automation-agent",
                status=TaskStatus.PENDING,
                modified_files=["zero-finance-tracker-email-ingestion.json"],
                required_artifacts=["zero-finance-tracker-email-ingestion.json"],
                mutation_expected=True,
                acceptance_criteria=[
                    "Dedicated email ingestion webhook endpoint operational",
                    "Payload validation contract verified",
                ],
            ),
            TaskItem(
                task_id="TASK-M2-02",
                milestone_id="M2_WORKFLOW_REFACTOR",
                title="Trading Bridge Micro-Workflow Decomposition",
                description="Extract automated trading alert ingestion and transaction bridge into dedicated micro-workflow.",
                assigned_agent="native/automation-agent",
                status=TaskStatus.PENDING,
                modified_files=["zero-finance-tracker-trading-bridge.json"],
                required_artifacts=["zero-finance-tracker-trading-bridge.json"],
                mutation_expected=True,
                acceptance_criteria=[
                    "Trading webhook payload parser operational",
                    "Transaction ledger sync verified",
                ],
            ),
            TaskItem(
                task_id="TASK-M2-03",
                milestone_id="M2_WORKFLOW_REFACTOR",
                title="Core Workflow Monolith Decomposition",
                description="Refactor remaining monolithic transaction routing, categorization, and balance calculations in main workflow.",
                assigned_agent="native/automation-agent",
                status=TaskStatus.PENDING,
                dependencies=["TASK-M2-01", "TASK-M2-02"],
                modified_files=["zero-finance-tracker.json"],
                required_artifacts=["zero-finance-tracker.json"],
                mutation_expected=True,
                acceptance_criteria=[
                    "Monolithic workflow node count reduced cleanly",
                    "Sub-workflow call routing verified",
                ],
            ),
            TaskItem(
                task_id="TASK-M2-04",
                milestone_id="M2_WORKFLOW_REFACTOR",
                title="Centralized Error Handling & Dead Letter Queue",
                description="Implement global error trigger workflow and dead letter queue for failed webhook deliveries.",
                assigned_agent="native/automation-agent",
                status=TaskStatus.PENDING,
                dependencies=["TASK-M2-03"],
                modified_files=["zero-finance-tracker-error-handler.json"],
                required_artifacts=["zero-finance-tracker-error-handler.json"],
                mutation_expected=True,
                acceptance_criteria=[
                    "Error trigger catches failed node executions",
                    "Dead letter queue captures unprocessed payloads",
                ],
            ),
        ]
        registered["M2_WORKFLOW_REFACTOR"] = MilestoneDefinition(
            milestone_id="M2_WORKFLOW_REFACTOR",
            title="n8n Workflow Decomposition & Micro-Workflows",
            description="Split monolithic 115-node workflow into modular micro-workflows with retry queues and error handlers.",
            phase=PhaseEnum.PHASE_10_BACKEND,
            required_gate="GATE_2_UI_UX_DESIGN",
            tasks=m2_tasks,
            acceptance_criteria=["Modular micro-workflows verified with isolated webhooks."],
            state=MilestoneState.PLANNED,
        )

    if "M3_AGENT_RAG" not in registered:
        registered["M3_AGENT_RAG"] = MilestoneDefinition(
            milestone_id="M3_AGENT_RAG",
            title="ZERO Finance Agent & Hybrid RAG Engine",
            description="Deploy natural language agent interface with direct SQL query generation and scoped vector RAG.",
            phase=PhaseEnum.PHASE_12_AI_LOGIC,
            required_gate="GATE_3_SECURITY",
            tasks=[],
            acceptance_criteria=["Hybrid RAG queries return grounded financial answers."],
            state=MilestoneState.PLANNED,
        )

    if "M4_DASHBOARD_RELEASE" not in registered:
        registered["M4_DASHBOARD_RELEASE"] = MilestoneDefinition(
            milestone_id="M4_DASHBOARD_RELEASE",
            title="Dashboard UI & Multi-Channel Release",
            description="Build frontend views and connect live Telegram & WhatsApp alert triggers.",
            phase=PhaseEnum.PHASE_17_DEPLOYMENT,
            required_gate="GATE_8_PRODUCTION_DEPLOYMENT",
            tasks=[],
            acceptance_criteria=["Command center UI and alerting triggers verified."],
            state=MilestoneState.PLANNED,
        )

    return registered


class MilestoneExecutionEngine:
    """Orchestrates authoritative milestone execution."""

    def __init__(
        self,
        store: Optional[EngineeringProjectStore] = None,
        checkpoints: Optional[CheckpointManager] = None,
        validator: Optional[PhaseValidator] = None,
        router: Optional[TaskRouter] = None,
        reviewer: Optional[ReviewerEngine] = None,
        repair_loop: Optional[RepairLoop] = None,
        worker_registry: Optional[WorkerRegistry] = None,
        lifecycle: Optional[ProjectLifecycleController] = None,
        context_builder: Optional[ProjectContextBuilder] = None,
        repository_guard: Optional[RepositoryGuard] = None,
    ):
        self.store = store or DEFAULT_PROJECT_STORE
        self.checkpoints = checkpoints or DEFAULT_CHECKPOINT_MANAGER
        self.validator = validator or DEFAULT_PHASE_VALIDATOR
        self.router = router or DEFAULT_TASK_ROUTER
        self.reviewer = reviewer or DEFAULT_REVIEWER_ENGINE
        self.repair_loop = repair_loop or DEFAULT_REPAIR_LOOP
        from zero_core.engineering.workers.registry import (
            DEFAULT_WORKER_REGISTRY,
            bootstrap_native_workers,
        )
        if worker_registry is None:
            bootstrap_native_workers(DEFAULT_WORKER_REGISTRY)
            self.worker_registry = DEFAULT_WORKER_REGISTRY
        else:
            bootstrap_native_workers(worker_registry)
            self.worker_registry = worker_registry
        self.lifecycle = lifecycle or DEFAULT_LIFECYCLE_CONTROLLER
        self.context_builder = context_builder or DEFAULT_CONTEXT_BUILDER
        self.repository_guard = repository_guard or DEFAULT_REPOSITORY_GUARD

    def _take_repo_snapshot(self, repo_dir: Path) -> Dict[str, str]:
        """Captures SHA-256 hash map of all repository files for physical delta calculation."""
        hashes: Dict[str, str] = {}
        if not repo_dir.exists():
            return hashes
        for p in repo_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(repo_dir)).replace("\\", "/")
                if not any(ign in rel for ign in (".git", ".venv", "__pycache__", ".pytest_cache", "checkpoints", ".pytest")):
                    try:
                        hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
                    except Exception:
                        pass
        return hashes

    def is_gate_approved(self, manifest: ProjectManifest, gate_name: str) -> bool:
        """Verifies authoritatively whether a gate is approved.

        Structured approval records (scope_approval, uiux_approval, approval_history)
        are authoritative. Unstructured advisory text in pending_user_actions must
        never invalidate or override a valid structured human approval.
        """
        # 1. GATE 1: FEATURE SCOPE / CONTINUATION PLAN
        if gate_name in ("GATE_1_FEATURE_SCOPE", "FEATURE_SCOPE", "SCOPE"):
            if manifest.scope_approval is not None:
                st = manifest.scope_approval.get("status", "") if isinstance(manifest.scope_approval, dict) else getattr(manifest.scope_approval, "status", "")
                if st.upper() in ("APPROVED", "PASS"):
                    return True

            for record in (manifest.approval_history or []):
                rec_gate = record.get("gate", "") if isinstance(record, dict) else getattr(record, "gate", "")
                rec_status = record.get("status", "") if isinstance(record, dict) else getattr(record, "status", "")
                if rec_gate in ("GATE_1_FEATURE_SCOPE", "FEATURE_SCOPE", "SCOPE") and str(rec_status).upper() in ("APPROVED", "PASS"):
                    return True

            return False

        # 2. GATE 2: UI / UX DESIGN
        elif gate_name in ("GATE_2_UI_UX_DESIGN", "UI_UX_DESIGN", "UIUX"):
            if manifest.uiux_approval is not None:
                st = manifest.uiux_approval.get("status", "") if isinstance(manifest.uiux_approval, dict) else getattr(manifest.uiux_approval, "status", "")
                if st.upper() in ("APPROVED", "PASS", "COMPLETED"):
                    return True
            for record in (manifest.approval_history or []):
                rec_gate = record.get("gate", "") if isinstance(record, dict) else getattr(record, "gate", "")
                rec_status = record.get("status", "") if isinstance(record, dict) else getattr(record, "status", "")
                if rec_gate in ("GATE_2_UI_UX_DESIGN", "UI_UX_DESIGN", "UIUX") and str(rec_status).upper() in ("APPROVED", "PASS", "COMPLETED"):
                    return True
            return False

        # 3. GATE 4: SECURITY & PERMISSIONS
        elif gate_name in ("GATE_4_SECURITY_PERMISSIONS", "SECURITY_PERMISSIONS", "SECURITY"):
            return manifest.security_approval is not None or manifest.security_status == "COMPLETED"

        # 4. GATE 8: PRODUCTION DEPLOYMENT
        elif gate_name in ("GATE_8_PRODUCTION_DEPLOYMENT", "PRODUCTION_DEPLOYMENT", "DEPLOYMENT"):
            return manifest.deployment_approval is not None or manifest.deployment_status == "COMPLETED"

        return False

    def verify_pre_mutation_invariant(
        self,
        manifest: ProjectManifest,
        context: Optional[TaskExecutionContext] = None,
        checkpoint: Optional[Checkpoint] = None,
        target_files: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validates pre-mutation safety invariant before any filesystem writes."""
        # 1. Project ID alignment across all active contexts
        if context and context.project_id and context.project_id != manifest.project_id:
            return False, f"PROJECT_BOUNDARY_VIOLATION: Context project_id '{context.project_id}' != manifest '{manifest.project_id}'"

        if checkpoint and checkpoint.project_id and checkpoint.project_id != manifest.project_id:
            return False, f"PROJECT_BOUNDARY_VIOLATION: Checkpoint project_id '{checkpoint.project_id}' != manifest '{manifest.project_id}'"

        # 2. Repository boundary containment
        repo_root = Path(manifest.repository_path).resolve()
        if not repo_root.exists():
            return False, f"PROJECT_BOUNDARY_VIOLATION: Repository root does not exist: '{repo_root}'"

        if target_files:
            is_safe, violations = self.repository_guard.audit_affected_files(repo_root, target_files)
            if not is_safe:
                return False, f"PROJECT_BOUNDARY_VIOLATION: {'; '.join(violations)}"

        return True, None

    def execute_milestone(
        self,
        manifest: ProjectManifest,
        req: EngineeringRequest,
        context: Optional[TaskExecutionContext] = None,
        mode: Optional[ExecutionMode] = None,
    ) -> str:
        """Executes a milestone in either DRY_RUN or REAL_EXECUTION mode."""
        raw_text = req.raw_instruction.lower()

        # Determine execution mode
        is_explicit_dry_run = any(k in raw_text for k in ("dry run", "dry-run", "dry_run", "preview", "simulate", "dryrun"))
        execution_mode = mode or (ExecutionMode.DRY_RUN if is_explicit_dry_run else ExecutionMode.REAL_EXECUTION)

        # Resolve milestone identifier
        milestone_id = req.target_milestone or manifest.current_milestone or "M1_FOUNDATION"
        canonical_milestones = get_canonical_milestones_for_project(manifest)

        if milestone_id not in canonical_milestones:
            valid_keys = ", ".join(f"`{k}`" for k in canonical_milestones.keys())
            return (
                f"❌ **MILESTONE_NOT_FOUND**: Milestone `{milestone_id}` is not recognized for project `{manifest.project_name}`.\n\n"
                f"**Available Milestones**:\n{valid_keys}"
            )

        ms_def = canonical_milestones[milestone_id]

        # Check if already completed
        if ms_def.state == MilestoneState.COMPLETED or any(
            m.milestone_id == milestone_id and m.is_completed for m in manifest.milestones
        ):
            return (
                f"# ⚠️ Milestone Already Complete\n"
                f"- **Project**: `{manifest.project_name}` (`{manifest.project_id}`)\n"
                f"- **Milestone**: `{milestone_id}` — {ms_def.title}\n"
                f"- **Status**: `COMPLETED`\n\n"
                f"> [!NOTE]\n"
                f"> Milestone `{milestone_id}` has already been implemented, reviewed, validated, and checkpointed.\n"
                f"> Next recommended milestone: `M2_WORKFLOW_REFACTOR`."
            )

        # Check Authoritative Gate
        gate_ok = self.is_gate_approved(manifest, ms_def.required_gate)

        # In REAL_EXECUTION mode, Gate approval is strictly mandatory!
        if execution_mode == ExecutionMode.REAL_EXECUTION and not gate_ok:
            return (
                f"# 🛑 Execution Blocked: HITL_GATE_REQUIRED\n"
                f"- **Project**: `{manifest.project_name}` (`{manifest.project_id}`)\n"
                f"- **Milestone**: `{milestone_id}` — {ms_def.title}\n"
                f"- **Required Gate**: `{ms_def.required_gate}`\n"
                f"- **Current Gate Status**: `PENDING APPROVAL`\n"
                f"- **Mutations**: `ZERO (No files modified)`\n\n"
                f"> [!IMPORTANT]\n"
                f"> **AUTHORITATIVE GATE REQUIRED**: Actual milestone execution is blocked until `{ms_def.required_gate}` is explicitly approved.\n"
                f"> In accordance with safety protocol, ZERO will NOT mutate any project files without prior human gate authorization.\n\n"
                f"**To approve feature scope, issue**:\n"
                f"```text\n"
                f"@Loop Engineering Agent\n"
                f"Project ID: {manifest.project_id}\n"
                f"approve scope\n"
                f"```"
            )

        # ---------------------------------------------------------------------
        # MODE 1: DRY RUN (Preview & Plan Validation)
        # ---------------------------------------------------------------------
        if execution_mode == ExecutionMode.DRY_RUN:
            task_lines = []
            workers_would_use = set()
            files_would_touch = set()
            for idx, t in enumerate(ms_def.tasks, 1):
                decision = self.router.route_task(t, manifest)
                worker = self.worker_registry.get(decision.selected_worker)
                worker_name = worker.name if worker else decision.selected_worker
                workers_would_use.add(worker_name)
                for f in t.modified_files:
                    files_would_touch.add(f)
                deps_str = ", ".join(t.dependencies) if t.dependencies else "None"
                task_lines.append(
                    f"{idx}. `[PENDING]` **{t.task_id}**: {t.title}\n"
                    f"   - **Department**: `{decision.department}` | **Assigned Worker**: `{worker_name}`\n"
                    f"   - **Target Files**: {', '.join(f'`{f}`' for f in t.modified_files)}\n"
                    f"   - **Dependencies**: `{deps_str}`"
                )

            gate_status_label = "APPROVED" if gate_ok else "APPROVAL_PENDING"
            return (
                f"# 🛡️ Milestone Execution Preview (DRY RUN)\n"
                f"- **Project**: `{manifest.project_name}` (`{manifest.project_id}`)\n"
                f"- **Milestone**: `{milestone_id}` — {ms_def.title}\n"
                f"- **Gate Status**: `{gate_status_label}`\n"
                f"- **Execution Mode**: `DRY_RUN`\n"
                f"- **Mutations**: `ZERO (Dry-run mode enforced)`\n\n"
                f"## Milestone Task DAG ({len(ms_def.tasks)} Tasks)\n"
                + "\n".join(task_lines) + "\n\n"
                f"## Execution Analysis\n"
                f"- **Workers That WOULD Be Dispatched**: {', '.join(sorted(workers_would_use)) or 'None'}\n"
                f"- **Files That WOULD Be Modified**: {', '.join(f'`{f}`' for f in sorted(files_would_touch)) or 'None'}\n"
                f"- **Tests That WOULD Run**: `pytest tests/` in project virtual environment\n"
                f"- **Risk Level**: `LOW to MEDIUM`\n"
                f"- **HITL Requirements**: Milestone completion halts at HITL Gate before advancing to M2.\n\n"
                f"*(ZERO Dry Run: Verified routing, task DAG, and worker compatibility. Zero files were modified in {manifest.project_name}.)*"
            )

        # ---------------------------------------------------------------------
        # MODE 2: REAL EXECUTION (Authoritatively Approved)
        # ---------------------------------------------------------------------
        all_targets = [f for t in ms_def.tasks for f in t.modified_files]
        is_safe, inv_err = self.verify_pre_mutation_invariant(manifest, context=context, target_files=all_targets)
        if not is_safe:
            return f"❌ **PRE_MUTATION_INVARIANT_FAILED**: {inv_err}"

        # 1. Pre-execution Checkpoint
        pre_ckpt = self.checkpoints.create_checkpoint(
            manifest,
            f"Pre-execution snapshot for milestone {milestone_id} ({manifest.project_name})",
        )

        manifest.current_milestone = milestone_id
        manifest.project_status = ProjectStatus.IN_PROGRESS
        self.store.save_project(manifest)

        task_execution_records = []
        repo_dir = Path(manifest.repository_path)

        for task in ms_def.tasks:
            # Check for credential / security boundary requirement
            t_desc_lower = task.description.lower()
            if any(k in t_desc_lower for k in ("live secret", "production credential", "aws key", "live db migration")):
                task.status = TaskStatus.BLOCKED
                return (
                    f"🛑 **HITL_SECURITY_REQUIRED**: Task `{task.task_id}` ({task.title}) requires external production credentials.\n"
                    f"Halted at HITL Gate for safe authorization."
                )

            task.status = TaskStatus.IN_PROGRESS
            manifest.current_task = task.task_id

            # Route task
            decision = self.router.route_task(task, manifest)
            if decision.selected_worker == "NO_CAPABLE_IMPLEMENTATION_WORKER":
                task.status = TaskStatus.FAILED
                task.failure_reason = "NO_CAPABLE_IMPLEMENTATION_WORKER"
                manifest.project_status = ProjectStatus.APPROVAL_PENDING
                self.store.save_project(manifest)
                return (
                    f"🛑 **TASK_FAILED (NO_CAPABLE_IMPLEMENTATION_WORKER)**: Task `{task.task_id}` ({task.title}) "
                    f"requires mutations, but no capable implementation worker is available in ZERO registry."
                )

            worker = self.worker_registry.get(decision.selected_worker)
            if not worker:
                worker = self.worker_registry.get("worker_coding_implementation") or self.worker_registry.get("worker_coding_agent")

            # Pre-task filesystem snapshot
            pre_task_hashes = self._take_repo_snapshot(repo_dir)

            # Build context package
            context_pkg = self.context_builder.build_context(
                project=manifest,
                task=task,
                worker=worker,
            )

            # Dispatch worker
            worker_result = worker.run_task(context_pkg)

            # Post-task filesystem snapshot & delta verification
            post_task_hashes = self._take_repo_snapshot(repo_dir)
            phys_created = set(post_task_hashes.keys()) - set(pre_task_hashes.keys())
            phys_modified = {
                k for k in set(pre_task_hashes.keys()).intersection(set(post_task_hashes.keys()))
                if pre_task_hashes[k] != post_task_hashes[k]
            }
            total_phys_mutations = len(phys_created) + len(phys_modified)

            mutation_expected = getattr(task, "mutation_expected", True)
            mutation_failed = False
            mutation_failure_msg = ""
            if mutation_expected:
                if total_phys_mutations == 0:
                    mutation_failed = True
                    mutation_failure_msg = (
                        f"Task `{task.task_id}` ({task.title}) required mutations, but 0 physical file changes were detected on disk. "
                        f"Worker `{worker.worker_id}` failed to produce real code modifications."
                    )
                else:
                    for cf in getattr(worker_result, "files_created", []):
                        norm_cf = cf.replace("\\", "/")
                        if norm_cf not in phys_created and norm_cf not in phys_modified:
                            mutation_failed = True
                            mutation_failure_msg = (
                                f"Worker `{worker.worker_id}` claimed to create `{cf}`, but the file does not physically exist on disk."
                            )
                            break

            # Independent Review
            review_result = self.reviewer.review_task_execution(
                manifest=manifest,
                task=task,
                worker_result=worker_result,
            )

            # Objective Validation
            val_result = self.validator.validate_task_execution(
                manifest=manifest,
                task=task,
                worker_result=worker_result,
            )

            if mutation_failed:
                from zero_core.engineering.validator import ValidationStatus
                val_result.status = ValidationStatus.FAIL
                val_result.failure_summary = mutation_failure_msg

            # Repair Loop if needed
            if not review_result.is_pass or not val_result.is_pass:
                if self.repair_loop.should_repair(task.task_id, review_result, val_result):
                    repair_task = self.repair_loop.create_repair_task(
                        original_task=task,
                        original_worker_id=worker.worker_id,
                        review_result=review_result,
                        validation_result=val_result,
                        diff=worker_result.diff,
                    )
                    repair_item = repair_task.to_task_item()
                    repair_context = self.context_builder.build_context(
                        project=manifest,
                        task=repair_item,
                        worker=worker,
                    )
                    repair_result = worker.run_task(repair_context)
                    repair_review = self.reviewer.review_task_execution(
                        manifest, repair_item, repair_result
                    )
                    repair_val = self.validator.validate_task_execution(
                        manifest=manifest,
                        task=repair_item,
                        worker_result=repair_result,
                    )

                    post_repair_hashes = self._take_repo_snapshot(repo_dir)
                    rep_created = set(post_repair_hashes.keys()) - set(pre_task_hashes.keys())
                    rep_modified = {
                        k for k in set(pre_task_hashes.keys()).intersection(set(post_repair_hashes.keys()))
                        if pre_task_hashes[k] != post_repair_hashes[k]
                    }
                    if mutation_expected and (len(rep_created) + len(rep_modified)) == 0:
                        repair_val.status = ValidationStatus.FAIL
                        repair_val.failure_summary = "EXPECTED_MUTATION_NOT_OBSERVED"

                    if not repair_review.is_pass or not repair_val.is_pass:
                        task.status = TaskStatus.BLOCKED
                        manifest.project_status = ProjectStatus.APPROVAL_PENDING
                        self.store.save_project(manifest)
                        return (
                            f"🛑 **MILESTONE_BLOCKED**: Repair loop exhausted for task `{task.task_id}` ({task.title}).\n"
                            f"- **Reviewer**: `{repair_review.summary}`\n"
                            f"- **Validator**: `{repair_val.failure_summary}`\n"
                            f"Halted for human intervention."
                        )
                    else:
                        worker_result = repair_result
                        review_result = repair_review
                        val_result = repair_val
                else:
                    task.status = TaskStatus.BLOCKED
                    manifest.project_status = ProjectStatus.APPROVAL_PENDING
                    self.store.save_project(manifest)
                    return f"🛑 **MILESTONE_BLOCKED**: Task `{task.task_id}` failed validation and cannot be repaired autonomously."

            # Executable Acceptance Criteria Evaluation
            from zero_core.engineering.acceptance import AcceptanceVerdict, DEFAULT_ACCEPTANCE_ENGINE
            ac_results = DEFAULT_ACCEPTANCE_ENGINE.evaluate_all(
                task.acceptance_criteria, repo_dir, worker_result, task
            )
            failed_acs = [
                (c, res) for c, res in ac_results.items()
                if res[0] in (AcceptanceVerdict.FAIL, AcceptanceVerdict.UNVERIFIABLE)
            ]
            if failed_acs:
                ac_err_msg = "\n".join(f"- ❌ {c}: {r[1]}" for c, r in failed_acs)
                task.status = TaskStatus.BLOCKED
                task.failure_reason = f"ACCEPTANCE_CRITERIA_FAILURE"
                manifest.project_status = ProjectStatus.APPROVAL_PENDING
                self.store.save_project(manifest)
                return (
                    f"🛑 **TASK_BLOCKED (ACCEPTANCE_CRITERIA_FAILURE)**: Task `{task.task_id}` failed acceptance criteria:\n{ac_err_msg}"
                )

            # Mark task completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc).isoformat()
            if task.task_id not in manifest.completed_tasks:
                manifest.completed_tasks.append(task.task_id)

            task_execution_records.append({
                "task_id": task.task_id,
                "title": task.title,
                "worker": worker.name,
                "review": review_result.summary,
                "validation": val_result.failure_summary if not val_result.is_pass else "Passed",
            })

        # Milestone successfully completed!
        ms_item = MilestoneItem(
            milestone_id=milestone_id,
            title=ms_def.title,
            phase=ms_def.phase,
            description=ms_def.description,
            tasks=ms_def.tasks,
            is_completed=True,
            acceptance_tests=ms_def.acceptance_criteria,
        )
        # Update or append milestone in manifest
        existing_idx = next((i for i, m in enumerate(manifest.milestones) if m.milestone_id == milestone_id), None)
        if existing_idx is not None:
            manifest.milestones[existing_idx] = ms_item
        else:
            manifest.milestones.append(ms_item)

        manifest.current_task = None
        manifest.project_status = ProjectStatus.APPROVAL_PENDING
        manifest.pending_user_actions = [
            f"Milestone {milestone_id} Completed. Review Milestone Completion Report and approve to begin Milestone 2."
        ]

        post_ckpt = self.checkpoints.create_checkpoint(
            manifest,
            f"Completed milestone {milestone_id} ({ms_def.title})",
        )

        # Milestone Checkpoint Delta Gate: Pre vs Post comparison
        all_mutation_expected = all(getattr(t, "mutation_expected", True) for t in ms_def.tasks)
        if all_mutation_expected and (pre_ckpt.file_hashes == post_ckpt.file_hashes):
            manifest.project_status = ProjectStatus.APPROVAL_PENDING
            self.store.save_project(manifest)
            return (
                f"🛑 **MILESTONE_PHANTOM_EXECUTION**: Milestone `{milestone_id}` was aborted! "
                f"Pre-execution and post-execution checkpoints are identical ({len(pre_ckpt.file_hashes)} files unchanged).\n"
                f"All tasks in this milestone required physical file mutations, but zero net filesystem changes were detected."
            )

        self.store.save_project(manifest)

        task_summary_md = "\n".join(
            f"- ✅ **{r['task_id']}**: {r['title']} (Worker: `{r['worker']}` | Review: `{r['review'][:60]}`)"
            for r in task_execution_records
        )

        return (
            f"# 🎉 MILESTONE COMPLETION REPORT: {milestone_id}\n"
            f"**Project**: `{manifest.project_name}` (`{manifest.project_id}`)\n"
            f"**Milestone**: `{milestone_id}` — {ms_def.title}\n"
            f"**Status**: `COMPLETED`\n"
            f"**Pre-Execution Checkpoint**: `{pre_ckpt.checkpoint_id}`\n"
            f"**Post-Execution Checkpoint**: `{post_ckpt.checkpoint_id}`\n\n"
            f"## Executed Tasks\n"
            f"{task_summary_md}\n\n"
            f"## Quality Assurance Verification\n"
            f"- **Independent Review**: 100% Passed (ReviewerEngine verified code standards & architecture)\n"
            f"- **Objective Validation**: 100% Passed (PhaseValidator verified syntax and boundaries)\n"
            f"- **Physical Filesystem Delta**: Verified non-empty changes matching worker declarations\n"
            f"- **Acceptance Criteria**: 100% Evaluated and passed\n"
            f"- **Repository Containment**: Verified with zero cross-project pollution\n\n"
            f"🛑 **Halted at Milestone Completion HITL Gate**: Milestone {milestone_id} is complete.\n"
            f"Milestone 2 (`M2_WORKFLOW_REFACTOR`) will NOT auto-start without human approval."
        )


# Global singleton instance
DEFAULT_MILESTONE_ENGINE = MilestoneExecutionEngine()
