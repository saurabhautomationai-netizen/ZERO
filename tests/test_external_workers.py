"""Unit and integration tests for ExternalEngineeringWorker base, registry, and transports."""

import json
from pathlib import Path
import pytest

from zero_core.engineering.departments.registry import DEFAULT_DEPARTMENT_REGISTRY
from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.external import (
    AntigravityWorker,
    ChatGPTWorker,
    ExternalEngineeringWorker,
)
from zero_core.engineering.workers.registry import (
    DEFAULT_WORKER_REGISTRY,
    WorkerRegistry,
    bootstrap_all_workers,
    bootstrap_external_workers,
)
from zero_core.engineering.workers.transport import TransportConfig, TransportType


class DummyExternalWorker(ExternalEngineeringWorker):
    def __init__(self, fail_times=0, **kwargs):
        super().__init__(
            worker_id="worker_dummy",
            name="Dummy Worker",
            worker_type=WorkerType.EXTERNAL_API,
            capabilities=[WorkerCapability.ARCHITECTURE],
            transport_config=TransportConfig(max_retries=2, retry_backoff_seconds=0.01),
            **kwargs,
        )
        self.fail_times = fail_times
        self.call_count = 0

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        def op():
            self.call_count += 1
            if self.call_count <= self.fail_times:
                raise ConnectionError("Temporary glitch")
            return "Success response"

        out = self.execute_with_retry(op)
        res = WorkerResult(
            task_id=context.task_id,
            worker_id=self.worker_id,
            status="SUCCESS",
            summary=out,
        )
        self.save_artifacts(context.task_id, {"req": "test"}, {"resp": out}, res)
        return res


def test_external_worker_base_contract(tmp_path):
    worker = DummyExternalWorker(artifacts_dir=tmp_path)
    assert worker.worker_id == "worker_dummy"
    assert worker.worker_type == WorkerType.EXTERNAL_API
    assert worker.has_capability(WorkerCapability.ARCHITECTURE)
    assert worker.health_check() == WorkerStatus.AVAILABLE


def test_external_worker_retry_success(tmp_path):
    worker = DummyExternalWorker(fail_times=2, artifacts_dir=tmp_path)
    context = ProjectContextPackage(
        task_id="t_retry_01",
        project_id="p_test",
        project_name="Test Project",
        current_phase="PHASE_1",
        task_title="Test Retry",
        task_description="Execute resilient operation",
    )
    res = worker.run_task(context)
    assert res.is_success
    assert res.summary == "Success response"
    assert worker.call_count == 3  # 2 failed + 1 success


def test_external_worker_retry_exhausted(tmp_path):
    worker = DummyExternalWorker(fail_times=5, artifacts_dir=tmp_path)
    context = ProjectContextPackage(
        task_id="t_retry_fail",
        project_id="p_test",
        project_name="Test Project",
        current_phase="PHASE_1",
        task_title="Test Fail",
        task_description="Execute failing operation",
    )
    with pytest.raises(ConnectionError):
        worker.run_task(context)


def test_artifact_persistence(tmp_path):
    worker = DummyExternalWorker(artifacts_dir=tmp_path)
    context = ProjectContextPackage(
        task_id="t_art_01",
        project_id="p_art",
        project_name="Artifact Project",
        current_phase="PHASE_1",
        task_title="Test Artifacts",
        task_description="Test artifact writing",
    )
    res = worker.run_task(context)
    assert res.is_success

    task_dir = tmp_path / "t_art_01"
    assert task_dir.exists()
    assert (task_dir / "request.json").exists()
    assert (task_dir / "response.json").exists()
    assert (task_dir / "result.json").exists()

    saved_result = json.loads((task_dir / "result.json").read_text(encoding="utf-8"))
    assert saved_result["task_id"] == "t_art_01"
    assert saved_result["status"] == "SUCCESS"


def test_bootstrap_external_workers():
    reg = WorkerRegistry()
    bootstrap_external_workers(reg)
    assert reg.get("worker_chatgpt") is not None
    assert reg.get("worker_antigravity") is not None

    chatgpt = reg.get("worker_chatgpt")
    assert chatgpt.has_capability(WorkerCapability.ARCHITECTURE_REVIEW)
    assert chatgpt.has_capability(WorkerCapability.CODE_REVIEW)

    antigravity = reg.get("worker_antigravity")
    assert antigravity.has_capability(WorkerCapability.CODE_GENERATION)
    assert antigravity.has_capability(WorkerCapability.TESTING)


def test_department_registry_external_workers():
    dept_reg = DEFAULT_DEPARTMENT_REGISTRY

    eng = dept_reg.get("engineering")
    assert "worker_chatgpt" in eng.member_worker_ids
    assert "worker_antigravity" in eng.member_worker_ids

    qa = dept_reg.get("qa")
    assert "worker_chatgpt" in qa.member_worker_ids

    product = dept_reg.get("product")
    assert "worker_chatgpt" in product.member_worker_ids

    research = dept_reg.get("research")
    assert "worker_chatgpt" in research.member_worker_ids
