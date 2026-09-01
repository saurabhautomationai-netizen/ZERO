"""Unit and integration tests for ZERO Engineering Worker & Department Registries."""

import pytest
from zero_core.engineering.departments.registry import (
    DEFAULT_DEPARTMENT_REGISTRY,
    DepartmentRegistry,
    DepartmentSpec,
)
from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.native import (
    CodingAgentWorker,
    ProjectBuilderWorker,
    ResearchWorker,
)
from zero_core.engineering.workers.registry import (
    DEFAULT_WORKER_REGISTRY,
    WorkerRegistry,
    WorkerSpec,
    bootstrap_native_workers,
)


class DummyCustomWorker(EngineeringWorker):
    """Synthetic worker for testing registry behaviors."""

    def __init__(self):
        super().__init__(
            worker_id="worker_dummy",
            name="Dummy Specialist",
            worker_type=WorkerType.NATIVE,
            capabilities=[WorkerCapability.TESTING, WorkerCapability.CODE_REVIEW],
            transport="INTERNAL_CALL",
            risk_level="LOW",
        )

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        return WorkerResult(
            task_id=context.task_id,
            worker_id=self.worker_id,
            status="SUCCESS",
            summary=f"Processed dummy task {context.task_title}",
            tests_executed=5,
            tests_passed=5,
        )


def test_worker_contract_properties():
    worker = DummyCustomWorker()
    assert worker.worker_id == "worker_dummy"
    assert worker.name == "Dummy Specialist"
    assert worker.worker_type == WorkerType.NATIVE
    assert worker.status == WorkerStatus.AVAILABLE
    assert worker.has_capability(WorkerCapability.TESTING)
    assert worker.has_capability("testing")
    assert not worker.has_capability(WorkerCapability.UI_DESIGN)

    worker.set_status(WorkerStatus.RATE_LIMITED)
    assert worker.status == WorkerStatus.RATE_LIMITED
    assert worker.health_check() == WorkerStatus.RATE_LIMITED


def test_worker_task_execution():
    worker = DummyCustomWorker()
    pkg = ProjectContextPackage(
        task_id="t_001",
        project_id="p_test",
        project_name="Test System",
        current_phase="PHASE_13_TESTING",
        task_title="Verify test coverage",
        task_description="Execute test suite and assert 0 failures",
        acceptance_criteria=["0 test failures"],
    )
    result = worker.run_task(pkg)
    assert isinstance(result, WorkerResult)
    assert result.task_id == "t_001"
    assert result.worker_id == "worker_dummy"
    assert result.is_success
    assert result.tests_passed == 5


def test_worker_registry_lifecycle():
    reg = WorkerRegistry()
    assert len(reg.list_workers()) == 0

    worker = DummyCustomWorker()
    reg.register(worker)
    assert len(reg.list_workers()) == 1
    assert reg.get("worker_dummy") is worker

    spec = reg.get_spec("worker_dummy")
    assert spec is not None
    assert spec.worker_id == "worker_dummy"
    assert "testing" in spec.capabilities

    # Find by capability
    testers = reg.find_by_capability(WorkerCapability.TESTING)
    assert len(testers) == 1
    assert testers[0] is worker

    designers = reg.find_by_capability(WorkerCapability.UI_DESIGN)
    assert len(designers) == 0

    # Best worker matching
    best = reg.get_best_worker_for_task([WorkerCapability.TESTING])
    assert best is worker

    # Unregister
    removed = reg.unregister("worker_dummy")
    assert removed is worker
    assert reg.get("worker_dummy") is None
    assert len(reg.list_workers()) == 0


def test_bootstrap_native_workers():
    reg = WorkerRegistry()
    bootstrap_native_workers(reg)
    workers = reg.list_workers()
    assert len(workers) == 3

    builder = reg.get("worker_project_builder")
    assert builder is not None
    assert builder.has_capability(WorkerCapability.SRS)
    assert builder.has_capability(WorkerCapability.ARCHITECTURE)

    coding = reg.get("worker_coding_agent")
    assert coding is not None
    assert coding.has_capability(WorkerCapability.CODE_GENERATION)
    assert coding.has_capability(WorkerCapability.TESTING)

    research = reg.get("worker_research_agent")
    assert research is not None
    assert research.has_capability(WorkerCapability.RESEARCH)

    health = reg.health_check_all()
    assert health["worker_project_builder"] == WorkerStatus.AVAILABLE
    assert health["worker_coding_agent"] == WorkerStatus.AVAILABLE


def test_native_project_builder_worker_execution():
    worker = ProjectBuilderWorker()
    pkg = ProjectContextPackage(
        task_id="t_builder_01",
        project_id="p_micro_saas",
        project_name="Micro SaaS Engine",
        current_phase="PHASE_2_SRS",
        task_title="Produce architecture specification",
        task_description="Build autonomous subscription manager",
        acceptance_criteria=["Functional SRS generated", "ADRs documented"],
    )
    result = worker.run_task(pkg)
    assert result.is_success
    assert "Micro SaaS Engine" in result.summary
    assert len(result.decisions) >= 1
    assert result.acceptance_criteria_results["Functional SRS generated"] is True


def test_native_coding_agent_worker_execution():
    worker = CodingAgentWorker()
    sample_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    pkg = ProjectContextPackage(
        task_id="t_coding_01",
        project_id="p_calc",
        project_name="Calculator",
        current_phase="PHASE_10_BACKEND",
        task_title="Review calculator logic",
        task_description="Inspect math handler",
        relevant_files={"math_handler.py": sample_code},
        acceptance_criteria=["Clean architecture compliant"],
    )
    result = worker.run_task(pkg)
    assert result.is_success
    assert "math_handler.py" in result.files_read


def test_native_research_worker_execution():
    worker = ResearchWorker()
    pkg = ProjectContextPackage(
        task_id="t_res_01",
        project_id="p_market",
        project_name="Market Analysis",
        current_phase="PHASE_1_DISCOVERY",
        task_title="Research modern vector databases",
        task_description="Compare pgvector vs Milvus vs Qdrant",
    )
    result = worker.run_task(pkg)
    assert result.is_success
    assert "research" in result.summary.lower()


def test_department_registry_defaults():
    dept_reg = DepartmentRegistry()
    depts = dept_reg.list_departments()
    assert len(depts) >= 14

    eng = dept_reg.get("engineering")
    assert eng is not None
    assert eng.name == "Software Engineering"
    assert "worker_coding_agent" in eng.member_worker_ids

    design = dept_reg.get("design")
    assert design is not None
    assert "design" in design.agency_divisions

    product = dept_reg.get("product")
    assert product is not None
    assert product.lead_worker_id == "worker_project_builder"


def test_department_task_mapping():
    dept_reg = DepartmentRegistry()
    
    code_dept = dept_reg.find_for_task("Fix the python fastAPI backend bug")
    assert code_dept.department_id == "engineering"

    ui_dept = dept_reg.find_for_task("Design a dark glassmorphic UI dashboard mockup with CSS grid")
    assert ui_dept.department_id == "design"

    test_dept = dept_reg.find_for_task("Run pytest automated test suite and check e2e coverage")
    assert test_dept.department_id == "qa"

    sec_dept = dept_reg.find_for_task("Perform security vulnerability audit and check for leaked API tokens")
    assert sec_dept.department_id == "security"

    prod_dept = dept_reg.find_for_task("Generate product roadmap and SRS user stories")
    assert prod_dept.department_id == "product"
