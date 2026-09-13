"""Synthetic G1 tests; run with --confcutdir to bypass runtime fixtures."""

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, EvidenceRecord, OperationRule, PermissionDecision,
    RequestedOperation, TaskPacket, WorkspacePolicy, canonical_json, fingerprint,
)


NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
ROOT = "C:/synthetic/project"
DIGEST = "a" * 64


def operation(**updates):
    return RequestedOperation(action="READ_FILE", target="src/main.py").model_copy(update=updates)


def packet(**updates):
    return TaskPacket(
        packet_id="packet-1", project_id="project-1", task_id="task-1",
        milestone_id="milestone-1", repository_root=ROOT, policy_id="policy-1",
        policy_version=1, context_fingerprint=DIGEST, operations=(operation(),),
        created_at=NOW,
    ).model_copy(update=updates)


def policy(**updates):
    return WorkspacePolicy(
        policy_id="policy-1", policy_version=1, project_id="project-1",
        repository_root=ROOT,
        rules=(OperationRule(operation=operation(), outcome="LOW_RISK"),),
    ).model_copy(update=updates)


def decision():
    return policy().evaluate(packet(), decision_id="decision-1", evaluated_at=NOW)


def result(**updates):
    return EngineeringExecutionResult(
        execution_id="execution-1", executor_id="worker-1", project_id="project-1",
        task_id="task-1", packet_fingerprint=packet().fingerprint(),
        permission_decision_id="decision-1", status="SUCCESS", started_at=NOW,
        finished_at=NOW, summary="Executor reported success; not verified.",
    ).model_copy(update=updates)


def evidence(**updates):
    return EvidenceRecord(
        evidence_id="evidence-1", project_id="project-1", task_id="task-1",
        execution_id="execution-1", execution_fingerprint=result().fingerprint(),
        check_id="syntax-1", producer_id="verifier-1", producer_kind="VERIFIER",
        outcome="PASS", summary="Synthetic verifier observation",
        artifact_path="evidence/syntax.json", artifact_sha256=DIGEST, observed_at=NOW,
    ).model_copy(update=updates)


@pytest.mark.parametrize("factory", [operation, packet, policy, decision, result, evidence])
def test_json_round_trip_and_canonical_fingerprint(factory):
    record = factory()
    restored = type(record).model_validate_json(record.model_dump_json())
    assert restored == record
    assert canonical_json(record) == restored.canonical_json()
    assert fingerprint(record) == restored.fingerprint()
    assert len(record.fingerprint()) == 64
    reversed_keys = dict(reversed(list(json.loads(record.model_dump_json()).items())))
    assert type(record).model_validate_json(json.dumps(reversed_keys)).fingerprint() == record.fingerprint()


@pytest.mark.parametrize("factory", [operation, packet, policy, decision, result, evidence])
@pytest.mark.parametrize("change", [{"surprise": True}, {"schema_version": 2}, {"schema_version": True}, {"schema_version": "1"}])
def test_strict_versions_and_unknown_fields(factory, change):
    with pytest.raises(ValidationError):
        factory().model_copy(update=change)


@pytest.mark.parametrize("action", ["read_file", "EXECUTE_SQL", "READ_FILE_EXTRA", "", 1])
def test_unknown_actions_rejected(action):
    with pytest.raises(ValidationError):
        operation(action=action)


@pytest.mark.parametrize("target", [
    "", ".", "..", "../other", "src/../other", "/absolute", "C:/absolute",
    "C:relative", "\\\\host\\share", "//host/share", "\\\\?\\C:\\file",
    "src\\main.py", "src//main.py", "src/./main.py", "src/", "src/file:stream",
    "src/%2e%2e/file", "src/file.", "src/file ", " src/file", "NUL.txt",
    "src/COM1", "src/LPT2.log", "src/file\x00", "src/file\n", "src/*.py",
])
def test_invalid_file_targets(target):
    with pytest.raises(ValidationError):
        operation(target=target)


@pytest.mark.parametrize("root", ["relative", "C:relative", "c:/lowercase", "C:\\repo", "//host/share", "/repo/../other", "/repo/", ""])
def test_invalid_roots(root):
    with pytest.raises(ValidationError):
        packet(repository_root=root)


@pytest.mark.parametrize("value", ["", "../id", "a/b", "a\\b", "a:b", "a b", "a\n", 42])
def test_invalid_persistence_ids(value):
    with pytest.raises(ValidationError):
        packet(task_id=value)


def test_timestamps_require_utc_and_monotonic_execution():
    for value in (datetime(2026, 9, 13), NOW.astimezone(timezone(timedelta(hours=1)))):
        with pytest.raises(ValidationError):
            packet(created_at=value)
    with pytest.raises(ValidationError):
        result(finished_at=NOW - timedelta(seconds=1))
    assert packet().created_at.utcoffset() == timedelta(0)


def test_empty_or_duplicate_operations_and_rules_rejected():
    for ops in ((), (operation(), operation())):
        with pytest.raises(ValidationError):
            packet(operations=ops)
    with pytest.raises(ValidationError):
        policy(rules=(OperationRule(operation=operation(), outcome="LOW_RISK"),
                      OperationRule(operation=operation(), outcome="DENIED")))


def test_unlisted_operations_deny_and_binding_mismatch_denies():
    assert policy(rules=()).classification(packet())[0] == "DENIED"
    assert policy().classification(packet(operations=(operation(target="other.py"),)))[0] == "DENIED"
    for updates in ({"project_id": "other"}, {"repository_root": "C:/other"},
                    {"policy_id": "other"}, {"policy_version": 2}):
        assert policy().classification(packet(**updates)) == ("DENIED", ("POLICY_BINDING_MISMATCH",))


@pytest.mark.parametrize("outcomes,expected", [
    (("LOW_RISK", "LOW_RISK"), "LOW_RISK"),
    (("LOW_RISK", "HITL_REQUIRED"), "HITL_REQUIRED"),
    (("HITL_REQUIRED", "LOW_RISK"), "HITL_REQUIRED"),
    (("HITL_REQUIRED", "DENIED"), "DENIED"),
    (("DENIED", "LOW_RISK"), "DENIED"),
])
def test_permission_precedence(outcomes, expected):
    ops = (operation(), operation(target="src/second.py"))
    rules = tuple(OperationRule(operation=op, outcome=outcome) for op, outcome in zip(ops, outcomes))
    assert policy(rules=rules).classification(packet(operations=ops))[0] == expected


def command(**updates):
    return RequestedOperation(action="RUN_COMMAND", command_id="unit-tests",
                              arguments=("--quiet",), working_directory=".").model_copy(update=updates)


@pytest.mark.parametrize("change", [
    {"command_id": "unit-tests-extra"}, {"command_id": "unit"},
    {"command_id": "Unit-tests"}, {"arguments": ("--quiet", "--extra")},
    {"working_directory": "tests"},
])
def test_exact_command_matching_not_prefixes(change):
    p = policy(rules=(OperationRule(operation=command(), outcome="LOW_RISK"),))
    assert p.classification(packet(operations=(command(),)))[0] == "LOW_RISK"
    assert p.classification(packet(operations=(command(**change),)))[0] == "DENIED"


@pytest.mark.parametrize("change", [
    {"command_id": "pytest -q"}, {"working_directory": "../other"},
    {"working_directory": ""}, {"arguments": ("--quiet; rm",)},
    {"arguments": "--quiet"}, {"target": "test.py"}, {"command_id": None},
])
def test_commands_have_no_arbitrary_shell_shape(change):
    with pytest.raises(ValidationError):
        command(**change)


def test_file_operation_cannot_smuggle_command_fields():
    with pytest.raises(ValidationError):
        operation(command_id="unit-tests")


@pytest.mark.parametrize("change", [
    {"packet_id": "packet-2"}, {"project_id": "project-2"}, {"task_id": "task-2"},
    {"milestone_id": "milestone-2"}, {"repository_root": "C:/other"},
    {"policy_id": "policy-2"}, {"policy_version": 2},
    {"context_fingerprint": "b" * 64}, {"created_at": NOW + timedelta(seconds=1)},
    {"operations": (RequestedOperation(action="DELETE_FILE", target="src/main.py"),)},
])
def test_every_packet_field_is_fingerprinted(change):
    changed = packet(**change)
    assert changed.fingerprint() != packet().fingerprint()
    with pytest.raises(ValueError):
        decision().validate_binding(changed, policy())


@pytest.mark.parametrize("change", [
    {"policy_id": "policy-2"}, {"policy_version": 2}, {"project_id": "other"},
    {"repository_root": "C:/other"}, {"rules": ()},
])
def test_policy_fingerprint_covers_all_fields(change):
    changed = policy(**change)
    assert changed.fingerprint() != policy().fingerprint()
    with pytest.raises(ValueError):
        decision().validate_binding(packet(), changed)


@pytest.mark.parametrize("outcome", ["HITL_REQUIRED", "DENIED"])
def test_no_approval_override_in_contracts(outcome):
    p = policy(rules=(OperationRule(operation=operation(), outcome=outcome),))
    d = p.evaluate(packet(), decision_id="decision-1", evaluated_at=NOW)
    assert not d.permits_unattended_execution(packet(), p)
    with pytest.raises(ValidationError):
        d.model_copy(update={"approved": True})
    with pytest.raises(ValueError):
        d.model_copy(update={"outcome": "LOW_RISK"}).validate_binding(packet(), p)


def test_low_risk_is_still_bound_and_models_are_frozen():
    assert decision().permits_unattended_execution(packet(), policy())
    with pytest.raises(ValidationError):
        packet().task_id = "other"
    with pytest.raises(ValidationError):
        packet().operations[0].target = "other.py"


@pytest.mark.parametrize("change", [
    {"tests_executed": -1}, {"tests_passed": -1}, {"tests_failed": -1},
    {"tests_skipped": -1}, {"tests_executed": 1}, {"tests_passed": 1},
    {"tests_executed": True}, {"tests_executed": "0"},
    {"tests_executed": 1, "tests_failed": 1},
])
def test_invalid_counts(change):
    with pytest.raises(ValidationError):
        result(**change)


def test_consistent_counts():
    r = result(status="FAILED", tests_executed=3, tests_passed=1, tests_failed=1, tests_skipped=1)
    assert r.tests_executed == 3


@pytest.mark.parametrize("change", [
    {"reported_files_created": ("a.py", "a.py")},
    {"reported_files_created": ("a.py",), "reported_files_modified": ("a.py",)},
    {"reported_files_created": ("a.py",), "reported_files_deleted": ("A.py",)},
    {"reported_files_modified": ("a.py",), "reported_files_deleted": ("a.py",)},
])
def test_contradictory_change_claims(change):
    with pytest.raises(ValidationError):
        result(**change)


@pytest.mark.parametrize("field", ["verified", "reviewed", "checkpoint_id", "milestone_completed"])
def test_worker_success_is_not_completion(field):
    assert result().status == "SUCCESS"
    with pytest.raises(ValidationError):
        result().model_copy(update={field: True})


@pytest.mark.parametrize("change", [
    {"project_id": "other"}, {"task_id": "other"},
    {"packet_fingerprint": "b" * 64}, {"permission_decision_id": "other"},
])
def test_execution_binding(change):
    with pytest.raises(ValueError):
        result(**change).validate_binding(packet(), decision(), policy())


def test_denied_cannot_have_a_successful_execution():
    p = policy(rules=())
    d = p.evaluate(packet(), decision_id="decision-1", evaluated_at=NOW)
    with pytest.raises(ValueError):
        result().validate_binding(packet(), d, p)
    result(status="BLOCKED").validate_binding(packet(), d, p)


@pytest.mark.parametrize("change", [
    {"project_id": "other"}, {"task_id": "other"}, {"execution_id": "other"},
    {"execution_fingerprint": "b" * 64}, {"producer_id": "worker-1"},
    {"observed_at": NOW - timedelta(seconds=1)},
])
def test_evidence_binding(change):
    with pytest.raises(ValueError):
        evidence(**change).validate_binding(result())


def test_worker_assertions_cannot_be_verifier_pass():
    with pytest.raises(ValidationError):
        evidence(producer_kind="WORKER")
    with pytest.raises(ValidationError):
        evidence(artifact_path=None, artifact_sha256=None)
    evidence(producer_kind="WORKER", outcome="BLOCKED").validate_binding(result())
    evidence().validate_binding(result())
    with pytest.raises(ValueError):
        evidence().validate_binding(result(summary="Changed claim"))


def test_json_unsafe_and_untyped_values_rejected():
    with pytest.raises(ValidationError):
        result(summary=object())
    with pytest.raises(ValidationError):
        result(tests_executed=float("nan"))
    with pytest.raises(ValidationError):
        packet(context_fingerprint="not-a-digest")


def test_module_has_only_pure_import_dependencies():
    path = Path(importlib.util.find_spec("zero_core.engineering_contracts").origin)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed = {"__future__", "hashlib", "json", "re", "datetime", "typing", "pydantic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] in allowed
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "exec", "eval", "__import__"}


def test_fresh_import_is_inert(tmp_path):
    # Fresh interpreter prevents this module's earlier test import from masking
    # side effects. Preload only declared dependencies, then block writes,
    # network/process events and every other ZERO module at import time.
    root = str(Path(__file__).resolve().parents[2])
    script = r'''
import sys, os, json, hashlib, re, typing
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.functional_validators import AfterValidator
sys.path.insert(0, sys.argv[1])
class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("zero_core.") and fullname != "zero_core.engineering_contracts":
            raise AssertionError("runtime import: " + fullname)
        if fullname.split(".")[0] in {"requests", "httpx", "urllib", "socket", "subprocess"}:
            raise AssertionError("network/process module import: " + fullname)
sys.meta_path.insert(0, Guard())
def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise AssertionError("write during import")
    if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.system", "subprocess.Popen"} or event.startswith("socket."):
        raise AssertionError("side effect: " + event)
sys.addaudithook(audit)
import zero_core.engineering_contracts
assert "zero_core.engineering" not in sys.modules
assert "zero_core.executors" not in sys.modules
print("INERT")
'''
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    completed = subprocess.run([sys.executable, "-B", "-c", script, root], cwd=tmp_path,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "INERT"
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before
