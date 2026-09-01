"""Unit and integration tests for Project Lifecycle Controller and Task DAG."""

import pytest
from pathlib import Path
from zero_core.engineering.lifecycle import (
    DEFAULT_LIFECYCLE_CONTROLLER,
    DAGTaskNode,
    ProjectLifecycleController,
    TaskDAG,
    TaskState,
)
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, TaskItem


def test_task_dag_dependencies_and_ready_evaluation():
    dag = TaskDAG()
    t1 = dag.add_task("t1", PhaseEnum.PHASE_7_DATABASE, "Schema Design", "Design tables")
    t2 = dag.add_task("t2", PhaseEnum.PHASE_10_BACKEND, "API Implementation", "Write endpoints", depends_on=["t1"])

    # Initially only t1 is ready
    ready = dag.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == "t1"

    # Complete t1 -> t2 becomes ready
    dag.mark_completed("t1", "Schema verified")
    ready_after = dag.get_ready_tasks()
    assert len(ready_after) == 1
    assert ready_after[0].task_id == "t2"


def test_task_dag_conflict_detection():
    dag = TaskDAG()
    dag.add_task("t1", PhaseEnum.PHASE_10_BACKEND, "Auth API", "Login", target_files=["auth.py", "models.py"])
    dag.add_task("t2", PhaseEnum.PHASE_10_BACKEND, "User API", "Profile", target_files=["user.py", "models.py"])

    tasks = list(dag.nodes.values())
    conflicts = dag.detect_conflicts(tasks)
    assert len(conflicts) > 0
    assert any("models.py" in c for c in conflicts)


def test_phase_entry_rules_gate_enforcement():
    controller = ProjectLifecycleController()
    manifest = ProjectManifest(
        project_id="p_test_entry",
        project_name="Entry Test Project",
        project_type="NEW_PROJECT",
        repository_path=".",
        description="Testing phase entry rules",
        current_phase=PhaseEnum.PHASE_1_DISCOVERY,
    )

    # Cannot enter SRS without Gate 1 Scope Approval
    can_enter_srs, reasons = controller.check_phase_entry(manifest, PhaseEnum.PHASE_2_SRS)
    assert can_enter_srs is False
    assert any("GATE 1" in r for r in reasons)

    # Approve scope -> now allowed into SRS
    manifest.scope_approval = "APPROVED"
    manifest.current_phase = PhaseEnum.PHASE_2_SRS
    can_enter_srs_approved, _ = controller.check_phase_entry(manifest, PhaseEnum.PHASE_2_SRS)
    assert can_enter_srs_approved is True


def test_phase_exit_rules_unfinished_tasks():
    controller = ProjectLifecycleController()
    manifest = ProjectManifest(
        project_id="p_test_exit",
        project_name="Exit Test Project",
        project_type="NEW_PROJECT",
        repository_path=".",
        description="Testing phase exit rules",
        current_phase=PhaseEnum.PHASE_10_BACKEND,
    )

    dag = controller.get_or_create_dag(manifest)
    dag.add_task("t_backend_01", PhaseEnum.PHASE_10_BACKEND, "Backend Task", "Do backend work")

    # Unfinished task blocks exit
    can_exit, exit_reasons = controller.check_phase_exit(manifest, PhaseEnum.PHASE_10_BACKEND)
    assert can_exit is False
    assert any("unfinished task" in r.lower() for r in exit_reasons)

    # Complete task -> allowed to exit
    dag.mark_completed("t_backend_01")
    can_exit_done, _ = controller.check_phase_exit(manifest, PhaseEnum.PHASE_10_BACKEND)
    assert can_exit_done is True


def test_progress_calculation():
    controller = ProjectLifecycleController()
    manifest = ProjectManifest(
        project_id="p_prog",
        project_name="Progress Project",
        project_type="NEW_PROJECT",
        repository_path=".",
        description="Calculate progress",
        current_phase=PhaseEnum.PHASE_1_DISCOVERY,
    )
    p1 = controller.calculate_progress_percentage(manifest)
    assert p1 < 20

    manifest.current_phase = PhaseEnum.PHASE_13_TESTING
    p2 = controller.calculate_progress_percentage(manifest)
    assert p2 >= 60

    manifest.current_phase = PhaseEnum.COMPLETED
    p3 = controller.calculate_progress_percentage(manifest)
    assert p3 == 100
