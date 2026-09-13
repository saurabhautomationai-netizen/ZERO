"""Isolated G5 checks: fake reviewers, fake clocks, fake identifier sources.

Nothing here calls Antigravity, Claude, Codex, Goose, an MCP server, a network
service, a subprocess reviewer or any real AI provider. Nothing here reads,
writes or inspects a ZERO runtime, data or checkpoint path: G5 performs no
filesystem access at all, so the repository roots used below are synthetic
lexically-valid paths, and ``tmp_path`` is used only to prove that importing and
running the module creates nothing on disk.

Requirements 72-76 (the existing G1, G2A, G2B, G3 and G4 suites still pass) are
proven by running those five suites separately, not from inside this module.
"""

import ast
import importlib.util
import inspect
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields
from datetime import timedelta
from pathlib import Path

import pytest

from zero_core.engineering_contracts import PermissionDecision
from zero_core.engineering_verification import ChangeObservation, VerificationVerdict
from zero_core.engineering_recovery import RecoveryAction, RecoveryState
import zero_core.engineering_review as review_module
from zero_core.engineering_review import (
    ArtifactSelection, DECISION_AUTHORITY, FINGERPRINT_KIND, FindingSeverity, IDENTITY_KIND,
    IndependentReviewBoundary, PROTOCOL_VERSION, ProvidedArtifact, REASON_CODES,
    ReviewArtifactType, ReviewDecision, ReviewDimension, ReviewError, ReviewFinding,
    ReviewPackage, ReviewRequest, ReviewResponse, ReviewVerdict, RemediationRequest,
    SCHEMA_VERSION, TrustedReviewerChannel, parse_review_response,
)


MODULE_PATH = Path(review_module.__file__).resolve()
SOURCE = MODULE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
TEST_ROOT = Path(__file__).resolve().parent
FIXTURE = TEST_ROOT / "fixtures" / "reviewer_fixture.py"
REPOSITORY_ROOT = TEST_ROOT.parents[1]


def load_fixture():
    specification = importlib.util.spec_from_file_location("g5_reviewer_fixture", FIXTURE)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


F = load_fixture()
V = VerificationVerdict
S = RecoveryState
A = RecoveryAction
D = ReviewDimension
T = ReviewArtifactType

VERDICT_STATES = {V.FAILED: S.FAILED, V.BLOCKED: S.BLOCKED, V.INCONCLUSIVE: S.INCONCLUSIVE}
SELECTION_ORDER = [(T.DOCUMENTATION_EXCERPT, F.DOC_PATH), (T.SOURCE_TEXT, F.SOURCE_PATH),
                   (T.TEST_TEXT, F.TEST_PATH)]


@pytest.fixture
def scenario():
    return F.Scenario()


def codes(decision):
    return decision.reason_codes


def assert_no_reviewer_call(instance, code=None):
    """Every ineligible path must be refused with zero reviewer invocations."""
    decision = instance.review()
    assert instance.reviewer.calls == []
    assert decision.verdict is ReviewVerdict.BLOCKED
    if code is not None:
        assert codes(decision) == (code,)
    assert decision.human_review_required is True
    assert decision.authorizes_execution is False
    return decision


# 1. Import is inert -------------------------------------------------------

def test_fresh_import_is_inert(tmp_path):
    """1. Importing G5 opens nothing, writes nothing and connects to nothing."""
    script = r'''
import sys, os
sys.path.insert(0, sys.argv[1])
import zero_core.engineering_contracts, zero_core.engineering_execution
import zero_core.engineering_verification, zero_core.engineering_recovery
import json, hashlib, re


class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"requests", "httpx", "urllib", "socket", "subprocess",
                                      "multiprocessing", "pickle", "sqlite3", "ctypes"}:
            raise AssertionError("forbidden import: " + fullname)
        if fullname.startswith("zero_core.") and fullname not in {
                "zero_core.engineering_review", "zero_core.engineering_contracts",
                "zero_core.engineering_execution", "zero_core.engineering_verification",
                "zero_core.engineering_recovery"}:
            raise AssertionError("runtime import: " + fullname)


sys.meta_path.insert(0, Guard())


def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            raise AssertionError("write during import")
    if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.system",
                 "subprocess.Popen", "sqlite3.connect"} or event.startswith("socket."):
        raise AssertionError("side effect: " + event)


sys.addaudithook(audit)
import zero_core.engineering_review
assert "zero_core.process_runner" not in sys.modules
print("INERT")
'''
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    completed = subprocess.run([sys.executable, "-B", "-c", script, str(REPOSITORY_ROOT)],
                               cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "INERT"
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")) == before


def test_module_never_reads_the_environment():
    """1/21. No environment access exists anywhere, not only at import time."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "environb", "getenv", "putenv", "unsetenv"}
        if isinstance(node, ast.Name):
            assert node.id not in {"environ", "getenv", "putenv"}


def test_module_imports_no_execution_persistence_or_network_capability():
    """65/66/67/68. No runner, executor, store, subprocess, socket or filesystem."""
    allowed = {"zero_core.engineering_contracts", "zero_core.engineering_verification",
               "zero_core.engineering_recovery"}
    banned_roots = {"subprocess", "socket", "requests", "httpx", "urllib", "multiprocessing",
                    "asyncio", "pickle", "yaml", "shutil", "ctypes", "threading", "importlib",
                    "sqlite3", "os", "io", "pathlib", "tempfile", "glob", "stat", "ssl", "http"}
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned_roots, alias.name
                assert not alias.name.startswith("zero_core.") or alias.name in allowed
        if isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] not in banned_roots, node.module
            assert not node.module.startswith("zero_core.") or node.module in allowed
    banned_names = {"ProcessRunner", "LocalProcessRunner", "StatelessAdapter", "execute_attempt",
                    "IndependentVerifier", "LocalWorkspaceObserver", "RecoveryStore",
                    "open_recovery_store", "RecoveryEvent", "Popen", "run", "system", "eval",
                    "exec", "compile", "__import__", "pickle", "open", "read_text", "write_text",
                    "unlink", "mkdir", "urlopen", "connect", "append", "executemany",
                    "executescript"}
    for node in ast.walk(TREE):
        if isinstance(node, (ast.Name, ast.Attribute)):
            label = node.id if isinstance(node, ast.Name) else node.attr
            assert label not in banned_names, label
            assert "milestone" not in label.lower(), label
            assert not any(agent in label.lower() for agent in
                           ("codex", "goose", "claude", "antigravity")), label


def test_full_review_performs_no_side_effect(tmp_path):
    """67/68. A complete review writes no file, opens no socket, spawns nothing."""
    script = r'''
import sys, os, importlib.util
sys.path.insert(0, sys.argv[1])
specification = importlib.util.spec_from_file_location("fixture", sys.argv[2])
fixture = importlib.util.module_from_spec(specification)
specification.loader.exec_module(fixture)
from zero_core.engineering_review import ReviewVerdict


def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            raise AssertionError("write during review")
    if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.system", "os.chmod",
                 "subprocess.Popen", "sqlite3.connect", "os.listdir", "os.scandir",
                 "shutil.copyfile"} or event.startswith("socket."):
        raise AssertionError("side effect: " + event)


sys.addaudithook(audit)
approved = fixture.Scenario().review()
assert approved.verdict is ReviewVerdict.APPROVED, approved.reason_codes
changes = fixture.Scenario(reviewer=fixture.RecordingReviewer(fixture.changes_requested_response))
decision = changes.review()
assert decision.verdict is ReviewVerdict.CHANGES_REQUESTED, decision.reason_codes
assert changes.boundary.remediation_request(decision).next_attempt == 2
print("NO_SIDE_EFFECT")
'''
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    completed = subprocess.run([sys.executable, "-B", "-c", script, str(REPOSITORY_ROOT),
                                str(FIXTURE)], cwd=tmp_path, capture_output=True, text=True,
                               timeout=180)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "NO_SIDE_EFFECT"
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")) == before


# 2. Eligible work reaches the reviewer ------------------------------------

def test_eligible_verified_attempt_invokes_the_reviewer(scenario):
    """2. G3 VERIFIED plus a valid G4 VERIFIED chain is the only eligible case."""
    decision = scenario.review()
    assert len(scenario.reviewer.calls) == 1
    request = scenario.reviewer.calls[0]
    assert type(request) is ReviewRequest
    assert decision.verdict is ReviewVerdict.APPROVED
    assert codes(decision) == ("REVIEW_APPROVED",)
    assert decision.review_id == request.package.review_id
    assert decision.checkpoint_fingerprint == scenario.checkpoint.fingerprint()
    assert decision.evidence_fingerprint == scenario.evidence.fingerprint()


# 3-14. The eligibility gate makes zero reviewer calls ---------------------

@pytest.mark.parametrize("verdict", [V.FAILED, V.BLOCKED, V.INCONCLUSIVE])
def test_non_verified_evidence_makes_zero_reviewer_calls(verdict):
    """3/4/5. FAILED, BLOCKED and INCONCLUSIVE G3 verdicts are never reviewed."""
    instance = F.Scenario()
    state = VERDICT_STATES[verdict]
    instance.evidence = instance.build_evidence(verdict=verdict)
    instance.checkpoint = instance.build_checkpoint(state=state, evidence=instance.evidence)
    instance.assessment = instance.build_assessment(
        state=state, action=A.REQUIRE_HUMAN_REVIEW, checkpoint=instance.checkpoint,
        reverification_required=True)
    assert_no_reviewer_call(instance, "VERIFICATION_NOT_VERIFIED")


def test_interrupted_recovery_state_makes_zero_reviewer_calls():
    """6. An interrupted attempt has no trustworthy VERIFIED durable state."""
    instance = F.Scenario()
    instance.checkpoint = instance.build_checkpoint(state=S.INTERRUPTED)
    instance.assessment = instance.build_assessment(
        state=S.INTERRUPTED, action=A.REVERIFY_WORKSPACE, checkpoint=instance.checkpoint,
        reverification_required=True)
    assert_no_reviewer_call(instance, "RECOVERY_STATE_NOT_VERIFIED")


def test_corrupt_recovery_assessment_makes_zero_reviewer_calls(scenario):
    """7. A corrupt G4 chain blocks; review never repairs or bypasses it."""
    scenario.assessment = scenario.corrupt_assessment()
    assert_no_reviewer_call(scenario, "RECOVERY_STATE_CORRUPT")


def test_requires_reverification_makes_zero_reviewer_calls():
    """6/7. REQUIRES_REVERIFICATION is not VERIFIED, so it is not reviewable."""
    instance = F.Scenario()
    instance.checkpoint = instance.build_checkpoint(state=S.REQUIRES_REVERIFICATION)
    instance.assessment = instance.build_assessment(
        state=S.REQUIRES_REVERIFICATION, action=A.REVERIFY_WORKSPACE,
        checkpoint=instance.checkpoint, reverification_required=True)
    assert_no_reviewer_call(instance, "RECOVERY_STATE_NOT_VERIFIED")


def test_denied_permission_makes_zero_reviewer_calls():
    """8. A denied operation is never described to a reviewer."""
    assert_no_reviewer_call(F.Scenario(outcome="DENIED"), "PERMISSION_DENIED")


def test_hitl_required_makes_zero_reviewer_calls():
    """9/55. Human authorization is a separate authority G5 cannot supply."""
    assert_no_reviewer_call(F.Scenario(outcome="HITL_REQUIRED"),
                            "HUMAN_AUTHORIZATION_REQUIRED")


def test_tampered_permission_decision_makes_zero_reviewer_calls(scenario):
    """10. A decision that does not match the exact policy evaluation blocks."""
    tampered = PermissionDecision(
        decision_id="decision", packet_fingerprint=scenario.packet.fingerprint(),
        policy_fingerprint=scenario.policy.fingerprint(), outcome="LOW_RISK",
        reason_codes=("OPERATOR_OVERRIDE",), evaluated_at=F.NOW)
    decision = scenario.boundary.review(**scenario.parts(decision=tampered))
    assert scenario.reviewer.calls == []
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("BINDING_INVALID",)


def test_stale_permission_decision_makes_zero_reviewer_calls(scenario):
    """10. A decision bound to a different packet is stale, never adapted."""
    other = F.Scenario()
    other_packet = other.packet.model_copy(update={"milestone_id": "stage-two"})
    stale = other.policy.evaluate(other_packet, decision_id="decision", evaluated_at=F.NOW)
    decision = scenario.boundary.review(**scenario.parts(decision=stale))
    assert scenario.reviewer.calls == []
    assert codes(decision) == ("BINDING_INVALID",)


def test_project_mismatch_makes_zero_reviewer_calls():
    """11. Trusted configuration owns the project identity."""
    instance = F.Scenario(project_id="other-project")
    instance.boundary = instance.build_boundary(
        config=instance.build_config(project_id=F.PROJECT))
    assert_no_reviewer_call(instance, "PROJECT_MISMATCH")


def test_root_mismatch_makes_zero_reviewer_calls():
    """12/15. A task-controlled root can never replace the trusted root."""
    instance = F.Scenario(root=F.OTHER_ROOT)
    instance.boundary = instance.build_boundary(config=instance.build_config(root=F.ROOT))
    assert_no_reviewer_call(instance, "ROOT_MISMATCH")


def test_review_api_accepts_no_root_reviewer_or_limit_argument():
    """15/17. Root, reviewer identity and limits are configuration, not input."""
    for method in (IndependentReviewBoundary.review, IndependentReviewBoundary.create_request,
                   IndependentReviewBoundary.check_eligibility):
        names = set(inspect.signature(method).parameters)
        assert not names & {"repository_root", "root", "reviewer", "reviewer_id",
                            "reviewer_provider_id", "max_findings", "required_dimensions",
                            "authorized_paths", "artifact_selection", "timeout_seconds"}


def test_task_mismatch_makes_zero_reviewer_calls():
    """13. The trusted task identity must match the packet exactly."""
    instance = F.Scenario(task_id="other-task")
    instance.boundary = instance.build_boundary(config=instance.build_config(task_id=F.TASK))
    assert_no_reviewer_call(instance, "TASK_MISMATCH")


def test_execution_mismatch_makes_zero_reviewer_calls():
    """13. A result from another execution is never reviewed as this one."""
    instance = F.Scenario()
    instance.boundary = instance.build_boundary(
        config=instance.build_config(execution_id="other-attempt"))
    assert_no_reviewer_call(instance, "EXECUTION_MISMATCH")


def test_evidence_fingerprint_mismatch_makes_zero_reviewer_calls(scenario):
    """14. The G3 evidence offered must be the one G4 durably recorded."""
    other = scenario.build_evidence(changes=ChangeObservation(
        created=(F.SOURCE_PATH,), unchanged=(F.DOC_PATH, F.TEST_PATH)))
    assert other.fingerprint() != scenario.evidence.fingerprint()
    scenario.checkpoint = scenario.build_checkpoint(evidence=other)
    scenario.assessment = scenario.build_assessment(checkpoint=scenario.checkpoint)
    assert_no_reviewer_call(scenario, "EVIDENCE_FINGERPRINT_MISMATCH")


def test_attempt_fingerprint_mismatch_makes_zero_reviewer_calls(scenario):
    """14. The durable attempt digest must match this exact execution result."""
    other = scenario.execution.model_copy(update={"summary": "A different bounded claim."})
    scenario.checkpoint = scenario.build_checkpoint(execution=other)
    scenario.assessment = scenario.build_assessment(checkpoint=scenario.checkpoint)
    assert_no_reviewer_call(scenario, "BINDING_INVALID")


def test_checkpoint_not_the_assessed_one_makes_zero_reviewer_calls(scenario):
    """7/14. The checkpoint reviewed must be the assessed last valid checkpoint."""
    scenario.checkpoint = scenario.build_checkpoint(checkpoint_id="checkpoint-0009")
    assert_no_reviewer_call(scenario, "CHECKPOINT_INVALID")


def test_verified_state_with_pending_reverification_makes_zero_reviewer_calls(scenario):
    """6. Any outstanding reverification requirement is disqualifying."""
    scenario.assessment = scenario.build_assessment(reverification_required=True)
    assert_no_reviewer_call(scenario, "RECOVERY_STATE_NOT_VERIFIED")


# 16-17. Independence ------------------------------------------------------

def test_reviewer_equal_to_executor_identity_blocks():
    """16. A component cannot independently review its own change."""
    with pytest.raises(ReviewError) as configured:
        F.Scenario().build_config(reviewer_id=F.EXECUTOR)
    assert configured.value.code == "REVIEWER_NOT_INDEPENDENT"

    instance = F.Scenario()
    config = instance.build_config(reviewer_id=F.EXECUTOR, executor_identities=())
    channel = TrustedReviewerChannel(F.EXECUTOR, F.REVIEWER_PROVIDER, instance.reviewer)
    instance.boundary = instance.build_boundary(config=config, channel=channel)
    assert_no_reviewer_call(instance, "REVIEWER_NOT_INDEPENDENT")


def test_unknown_reviewer_channel_blocks(scenario):
    """17. Identity is the injected channel, checked against trusted config."""
    channel = TrustedReviewerChannel("reviewer-omega", F.REVIEWER_PROVIDER, scenario.reviewer)
    with pytest.raises(ReviewError) as error:
        scenario.build_boundary(channel=channel)
    assert error.value.code == "REVIEWER_UNKNOWN"
    assert scenario.reviewer.calls == []


def test_unknown_reviewer_provider_in_response_blocks(scenario):
    """17. A response may not rename its own provider."""
    request = scenario.request()
    answer = F.response(request, provider_id="reviewer-provider-omega")
    decision = scenario.boundary.evaluate_response(request, answer)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "REVIEWER_UNKNOWN" in codes(decision)


def test_channel_without_a_review_port_blocks():
    """17. An object that cannot review is not a reviewer."""
    with pytest.raises(ReviewError) as error:
        TrustedReviewerChannel(F.REVIEWER, F.REVIEWER_PROVIDER, object())
    assert error.value.code == "REVIEWER_UNKNOWN"


def test_independence_is_documented_as_configuration_not_authentication():
    """17. The identity claim is explicit and deliberately modest."""
    assert IDENTITY_KIND == "INJECTED_TRUSTED_CHANNEL_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED"
    assert F.Scenario().request().identity_kind == IDENTITY_KIND


# 18-23. The review package ------------------------------------------------

def test_review_package_is_deterministic():
    """18/70. Same inputs, same clock, same identifiers, same bytes."""
    first = F.Scenario().request()
    second = F.Scenario().request()
    assert first.package.canonical_json() == second.package.canonical_json()
    assert first.package.fingerprint() == second.package.fingerprint()
    assert first.fingerprint() == second.fingerprint()
    assert first.package.fingerprint() == first.package_fingerprint


def test_package_contents_are_exactly_the_bounded_set(scenario):
    """18/24. Only what an independent reviewer genuinely needs is present."""
    package = scenario.request().package
    assert package.schema_version == SCHEMA_VERSION
    assert package.protocol_version == PROTOCOL_VERSION
    assert package.project_id == F.PROJECT and package.task_id == F.TASK
    assert package.execution_id == F.EXECUTION and package.checkpoint_id == F.CHECKPOINT
    assert package.authorized_paths == F.AUTHORIZED
    assert package.required_dimensions == F.REQUIRED_DIMENSIONS
    assert package.created_at == scenario.clock.value
    assert package.fingerprint_kind == FINGERPRINT_KIND
    assert package.instruction_authority == "ZERO_TRUSTED_CONFIGURATION_ONLY"
    assert package.changes.created == (F.SOURCE_PATH, F.TEST_PATH)
    assert tuple(c.command_id for c in package.verification_commands) == ("pytest-g5",)
    assert package.verification_commands[0].verdict is V.VERIFIED
    names = {item.name for item in fields(ReviewPackage)}
    assert not names & {"repository_root", "environment", "prompt", "prompts", "session",
                        "session_id", "history", "transcript", "credentials", "secrets",
                        "stdout", "stderr", "executor_summary", "summary"}


@pytest.mark.parametrize("mutation", ["artifact", "paths", "evidence", "checkpoint",
                                      "dimensions", "root"])
def test_package_fingerprint_changes_on_any_verdict_relevant_mutation(mutation):
    """19. Nothing verdict-relevant can change without changing the digest."""
    base = F.Scenario().request().package.fingerprint()
    if mutation == "artifact":
        table = dict(F.ARTIFACT_CONTENT)
        table[(T.SOURCE_TEXT, F.SOURCE_PATH)] = "def add(left, right):\n    return left - right\n"
        instance = F.Scenario(provider=F.StaticArtifactProvider(table))
    elif mutation == "paths":
        instance = F.Scenario()
        instance.boundary = instance.build_boundary(config=instance.build_config(
            authorized_paths=F.AUTHORIZED + ("src/extra.py",)))
    elif mutation == "evidence":
        instance = F.Scenario()
        instance.evidence = instance.build_evidence(tests=(F.verified_test("pytest-other"),))
        instance.checkpoint = instance.build_checkpoint(evidence=instance.evidence)
        instance.assessment = instance.build_assessment(checkpoint=instance.checkpoint)
    elif mutation == "checkpoint":
        instance = F.Scenario()
        instance.checkpoint = instance.build_checkpoint(checkpoint_id="checkpoint-0006")
        instance.assessment = instance.build_assessment(checkpoint=instance.checkpoint)
    elif mutation == "dimensions":
        instance = F.Scenario()
        instance.boundary = instance.build_boundary(config=instance.build_config(
            required_dimensions=F.REQUIRED_DIMENSIONS + (D.MAINTAINABILITY,)))
    else:
        instance = F.Scenario(root="/synthetic-third-root")
    assert instance.request().package.fingerprint() != base


def test_package_carries_no_credential_environment_prompt_or_session_history(scenario):
    """20/21/22. Every forbidden marker is absent from the whole request."""
    request = scenario.request()
    text = request.canonical_json()
    for marker in (F.SECRET_SUMMARY, F.SECRET_CREDENTIAL, F.SECRET_ENVIRONMENT,
                   F.SECRET_PROMPT, F.SECRET_SESSION):
        assert marker not in text
    assert scenario.root not in text
    assert request.package.root_digest == F.digest(scenario.root)


def test_executor_prose_is_never_presented_as_verified_fact(scenario):
    """23. The reviewer sees G3 observations and digests, never executor claims."""
    request = scenario.request()
    text = request.canonical_json()
    assert scenario.execution.status == "SUCCESS"
    assert F.SECRET_SUMMARY not in text
    assert "SUCCESS" not in text
    assert request.package.execution_fingerprint == scenario.execution.fingerprint()
    for reported in scenario.execution.reported_files_created:
        assert reported in request.package.changes.created  # observed, not claimed


# 24-33. The artifact boundary ---------------------------------------------

def test_exactly_the_authorized_artifacts_are_supplied(scenario):
    """24. Selection is trusted configuration; only it is ever requested."""
    request = scenario.request()
    assert scenario.provider.requests == SELECTION_ORDER
    supplied = tuple((a.artifact_type, a.path) for a in request.package.artifacts)
    assert supplied == (
        (T.DOCUMENTATION_EXCERPT, F.DOC_PATH), (T.EVIDENCE_SUMMARY, None),
        (T.SOURCE_TEXT, F.SOURCE_PATH), (T.TEST_TEXT, F.TEST_PATH))
    for artifact in request.package.artifacts:
        assert artifact.byte_length == len(artifact.content.encode("utf-8"))
        assert artifact.content_digest == F.digest(artifact.content)
        assert artifact.content_kind == "UNTRUSTED_ARTIFACT_CONTENT_NOT_INSTRUCTIONS"


def test_evidence_summary_artifact_is_synthesised_by_zero(scenario):
    """24. No provider may supply or substitute the G3 evidence summary."""
    with pytest.raises(ReviewError):
        ArtifactSelection(T.EVIDENCE_SUMMARY, F.DOC_PATH)
    request = scenario.request()
    summary = [a for a in request.package.artifacts if a.artifact_type is T.EVIDENCE_SUMMARY][0]
    payload = json.loads(summary.content)
    assert payload["verdict"] == "VERIFIED"
    assert payload["evidence_fingerprint"] == scenario.evidence.fingerprint()
    assert (T.EVIDENCE_SUMMARY, None) not in scenario.provider.requests


def test_unexpected_artifact_path_blocks():
    """25. A provider may not substitute a different path for a selection."""
    table = dict(F.ARTIFACT_CONTENT)
    table[(T.SOURCE_TEXT, F.SOURCE_PATH)] = ProvidedArtifact(
        T.SOURCE_TEXT, "src/other.py", "x = 1\n")
    instance = F.Scenario(provider=F.StaticArtifactProvider(table))
    decision = assert_no_reviewer_call(instance, "ARTIFACT_PATH_UNTRUSTED")
    assert decision.package_fingerprint is None


@pytest.mark.parametrize("path", [
    "/etc/passwd", "C:/Windows/System32/drivers/etc/hosts", "../outside/module.py",
    "src/../../module.py", "src/module.py:secret", "src/module.py::$DATA",
    "//server/share/module.py", "\\\\?\\C:\\module.py", "src/\x00module.py",
    "src/nul.py", "src/module.py ", "src/module.py.", "src/<script>.py",
])
def test_absolute_traversal_stream_device_and_nul_paths_block(path):
    """26. Every ambiguous spelling is rejected lexically, before any use."""
    with pytest.raises(ReviewError):
        ArtifactSelection(T.SOURCE_TEXT, path)
    instance = F.Scenario()
    with pytest.raises(ReviewError):
        instance.build_config(authorized_paths=F.AUTHORIZED + (path,))
    assert instance.reviewer.calls == []


@pytest.mark.parametrize("state", ["SYMLINK", "REPARSE", "DIRECTORY", "SPECIAL",
                                   "MISSING", "UNAVAILABLE", "UNKNOWN_STATE"])
def test_symlink_junction_and_reparse_artifacts_block(state):
    """27. Anything but an exact REGULAR observation fails closed."""
    instance = F.Scenario(provider=F.StaticArtifactProvider(path_state=state))
    assert_no_reviewer_call(instance, "ARTIFACT_PATH_UNTRUSTED")


def test_duplicate_and_case_fold_colliding_paths_block():
    """28. Windows aliases both spellings, so both are refused everywhere."""
    instance = F.Scenario()
    with pytest.raises(ReviewError):
        instance.build_config(authorized_paths=F.AUTHORIZED + ("src/Module.py",))
    with pytest.raises(ReviewError):
        instance.build_config(
            artifact_selection=F.SELECTION + (ArtifactSelection(T.SOURCE_TEXT, F.SOURCE_PATH),))
    with pytest.raises(ReviewError):
        instance.build_config(
            artifact_selection=F.SELECTION + (ArtifactSelection(T.SOURCE_DIFF, F.SOURCE_PATH),))
    assert instance.reviewer.calls == []


def test_oversized_artifact_blocks_before_any_reviewer_call():
    """29. Per-artifact limits are enforced before the boundary is crossed."""
    table = dict(F.ARTIFACT_CONTENT)
    table[(T.SOURCE_TEXT, F.SOURCE_PATH)] = "y = 1\n" * 200
    instance = F.Scenario(provider=F.StaticArtifactProvider(table))
    instance.boundary = instance.build_boundary(
        config=instance.build_config(max_artifact_bytes=64))
    assert_no_reviewer_call(instance, "ARTIFACT_LIMIT")


def test_too_many_artifacts_block_before_any_reviewer_call():
    """30. The artifact count limit is trusted configuration, checked first."""
    instance = F.Scenario()
    with pytest.raises(ReviewError) as error:
        instance.build_config(max_artifacts=2)
    assert error.value.code == "ARTIFACT_LIMIT"
    object.__setattr__(instance.config, "max_artifacts", 1)
    decision = instance.review()
    assert instance.reviewer.calls == []
    assert decision.verdict is ReviewVerdict.BLOCKED


def test_excessive_total_package_size_blocks_before_any_reviewer_call():
    """31. The whole package is bounded, not only each artifact."""
    instance = F.Scenario()
    instance.boundary = instance.build_boundary(
        config=instance.build_config(max_package_bytes=1024))
    assert_no_reviewer_call(instance, "PACKAGE_LIMIT")


def test_artifact_truncation_never_approves():
    """32. A partial diff is never reviewed and never silently shortened."""
    instance = F.Scenario(provider=F.StaticArtifactProvider(truncated=True))
    assert_no_reviewer_call(instance, "ARTIFACT_TRUNCATED")


def test_artifact_provider_failure_never_approves():
    """32. A provider exception carries no detail into the decision."""
    instance = F.Scenario(provider=F.StaticArtifactProvider(
        failure=RuntimeError(F.SECRET_CREDENTIAL)))
    decision = assert_no_reviewer_call(instance, "ARTIFACT_INVALID")
    assert F.SECRET_CREDENTIAL not in decision.canonical_json()


def test_prompt_injection_inside_an_artifact_cannot_alter_the_review_contract():
    """33. Artifact content is data. It cannot move a boundary or a schema."""
    table = dict(F.ARTIFACT_CONTENT)
    table[(T.SOURCE_TEXT, F.SOURCE_PATH)] = F.INJECTION_TEXT
    obedient = F.RecordingReviewer(
        lambda request: F.response(request, dimensions=(), findings=()))
    instance = F.Scenario(provider=F.StaticArtifactProvider(table), reviewer=obedient)
    request = instance.request()
    assert request.required_dimensions == F.REQUIRED_DIMENSIONS
    assert request.package.required_dimensions == F.REQUIRED_DIMENSIONS
    assert request.verdict_schema == ("APPROVED", "CHANGES_REQUESTED", "BLOCKED", "INCONCLUSIVE")
    assert request.severity_schema == ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")
    assert request.max_findings == instance.config.max_findings
    injected = [a for a in request.package.artifacts if a.path == F.SOURCE_PATH][0]
    assert injected.content == F.INJECTION_TEXT
    assert injected.content_kind == "UNTRUSTED_ARTIFACT_CONTENT_NOT_INSTRUCTIONS"
    decision = instance.review()
    assert decision.verdict is ReviewVerdict.INCONCLUSIVE
    assert codes(decision) == ("REQUIRED_DIMENSION_NOT_REVIEWED",)
    with pytest.raises(ValueError):
        ReviewVerdict("SHIP_IT")


# 34-46. The strict response schema ---------------------------------------

def test_exact_bound_structured_approved_response_succeeds(scenario):
    """34. The only route to APPROVED is an exactly bound structured answer."""
    request = scenario.request()
    answer = F.response(request)
    decision = scenario.boundary.evaluate_response(request, answer)
    assert decision.verdict is ReviewVerdict.APPROVED
    assert decision.request_fingerprint == request.fingerprint()
    assert decision.response_fingerprint == answer.fingerprint()
    assert decision.remediation_required is False


def test_structured_json_payload_is_accepted(scenario):
    """34. A provider adapter may speak JSON; the schema is still exact."""
    request = scenario.request()
    payload = F.response_payload(F.response(request))
    decision = scenario.boundary.evaluate_response(request, json.dumps(payload))
    assert decision.verdict is ReviewVerdict.APPROVED


def test_mismatched_package_fingerprint_blocks(scenario):
    """35. A response is bound to one exact package, or it is refused."""
    request = scenario.request()
    answer = F.response(request, package_fingerprint="f" * 64)
    decision = scenario.boundary.evaluate_response(request, answer)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "PACKAGE_FINGERPRINT_MISMATCH" in codes(decision)


def test_unknown_or_missing_response_field_blocks(scenario):
    """36. Unknown fields are never ignored, merged or tolerated."""
    request = scenario.request()
    payload = F.response_payload(F.response(request))
    payload["override_zero"] = True
    decision = scenario.boundary.evaluate_response(request, payload)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("RESPONSE_SCHEMA_INVALID",)
    missing = F.response_payload(F.response(request))
    del missing["truncated"]
    assert scenario.boundary.evaluate_response(request, missing).verdict is ReviewVerdict.BLOCKED


def test_unknown_verdict_or_severity_blocks(scenario):
    """37. The verdict and severity vocabularies are closed."""
    request = scenario.request()
    payload = F.response_payload(F.response(request))
    payload["verdict"] = "SHIP_IT"
    assert scenario.boundary.evaluate_response(request, payload).verdict is ReviewVerdict.BLOCKED
    payload = F.response_payload(F.response(request, verdict=ReviewVerdict.CHANGES_REQUESTED,
                                            findings=(F.finding(remediation_required=True),)))
    payload["findings"][0]["severity"] = "CATASTROPHIC"
    decision = scenario.boundary.evaluate_response(request, payload)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("RESPONSE_SCHEMA_INVALID",)


def test_duplicate_finding_identifiers_and_duplicate_findings_block(scenario):
    """38. Duplicate finding IDs and duplicate findings are both refused."""
    request = scenario.request()
    duplicated = (F.finding(finding_id="finding-0001", reason_code="NIT_ONE"),
                  F.finding(finding_id="finding-0001", reason_code="NIT_TWO"))
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.INCONCLUSIVE, findings=duplicated))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "FINDING_DUPLICATE" in codes(decision)
    same = (F.finding(finding_id="finding-0001"), F.finding(finding_id="finding-0002"))
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.INCONCLUSIVE, findings=same))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "FINDING_DUPLICATE" in codes(decision)


def test_excessive_findings_block():
    """39. The finding count is bounded by trusted configuration."""
    instance = F.Scenario()
    instance.boundary = instance.build_boundary(config=instance.build_config(max_findings=2))
    request = instance.request()
    many = tuple(F.finding(finding_id="finding-%04d" % index, reason_code="NIT_%d" % index)
                 for index in range(3))
    decision = instance.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.INCONCLUSIVE, findings=many))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "FINDING_LIMIT" in codes(decision)


def test_oversized_finding_summary_blocks():
    """40. Summaries are bounded; nothing is truncated into acceptability."""
    instance = F.Scenario()
    instance.boundary = instance.build_boundary(
        config=instance.build_config(max_summary_length=32))
    request = instance.request()
    decision = instance.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.INCONCLUSIVE,
                            findings=(F.finding(summary="s" * 64),)))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "FINDING_SUMMARY_LIMIT" in codes(decision)


def test_finding_outside_the_authorized_paths_blocks(scenario):
    """41/58. A reviewer cannot invent a file, let alone a fact about one."""
    request = scenario.request()
    outside = F.finding(path="src/never_authorized.py", remediation_required=True)
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.CHANGES_REQUESTED,
                            findings=(outside,)))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "FINDING_PATH_UNAUTHORIZED" in codes(decision)
    with pytest.raises(ReviewError):
        F.finding(path="/etc/passwd")


def test_finding_referencing_an_unknown_artifact_blocks(scenario):
    """42. A finding may only cite an artifact that was actually supplied."""
    request = scenario.request()
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.INCONCLUSIVE,
                            findings=(F.finding(artifact_digest="a" * 64),)))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "FINDING_ARTIFACT_UNKNOWN" in codes(decision)
    known = F.finding(artifact_digest=request.package.artifacts[0].content_digest)
    allowed = scenario.boundary.evaluate_response(request, F.response(request, findings=(known,)))
    assert allowed.verdict is ReviewVerdict.APPROVED


def test_missing_required_dimension_is_inconclusive(scenario):
    """43. An incomplete review is inconclusive, never approved."""
    request = scenario.request()
    partial = F.response(request, dimensions=(D.CORRECTNESS, D.SECURITY))
    decision = scenario.boundary.evaluate_response(request, partial)
    assert decision.verdict is ReviewVerdict.INCONCLUSIVE
    assert codes(decision) == ("REQUIRED_DIMENSION_NOT_REVIEWED",)
    assert decision.human_review_required is True


@pytest.mark.parametrize("value", ["not-a-timestamp", "2026-09-13", "2026-09-13T00:00:00",
                                   "2026-09-13T00:00:00+05:30", "", 0])
def test_malformed_timestamp_blocks(scenario, value):
    """44. Only an unambiguous UTC instant is accepted."""
    request = scenario.request()
    payload = F.response_payload(F.response(request))
    payload["completed_at"] = value
    decision = scenario.boundary.evaluate_response(request, payload)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("RESPONSE_SCHEMA_INVALID",)


def test_truncated_response_never_approves(scenario):
    """45. A response that admits it is partial cannot approve anything."""
    request = scenario.request()
    decision = scenario.boundary.evaluate_response(request, F.response(request, truncated=True))
    assert decision.verdict is ReviewVerdict.INCONCLUSIVE
    assert "RESPONSE_TRUNCATED" in codes(decision)


@pytest.mark.parametrize("payload", ["", "APPROVED", "null", "[]", "42",
                                     "## Verdict\n\n**APPROVED**\n"])
def test_malformed_response_never_approves(scenario, payload):
    """45/46. There is no prose, Markdown or pattern-matching path to APPROVED."""
    request = scenario.request()
    decision = scenario.boundary.evaluate_response(request, payload)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision)[0] in ("RESPONSE_MALFORMED", "RESPONSE_SCHEMA_INVALID")


def test_reviewer_prose_cannot_be_parsed_as_approval():
    """46. Pasted or generated prose is never authoritative approval."""
    instance = F.Scenario(reviewer=F.ProseReviewer())
    decision = instance.review()
    assert len(instance.reviewer.calls) == 1
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("RESPONSE_MALFORMED",)
    assert "APPROVED" not in decision.canonical_json()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"search", "match", "findall", "splitlines", "lower",
                                     "upper", "strip", "startswith", "endswith"}


def test_reviewer_exception_never_approves():
    """47. No provider exception text, traceback or partial answer escapes."""
    instance = F.Scenario(reviewer=F.FailingReviewer())
    decision = instance.review()
    assert len(instance.reviewer.calls) == 1
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("REVIEWER_ERROR",)
    assert F.SECRET_CREDENTIAL not in decision.canonical_json()


def test_reviewer_unavailable_or_timeout_never_approves():
    """48. An unavailable reviewer is inconclusive, never permissive."""
    instance = F.Scenario(reviewer=F.UnavailableReviewer())
    decision = instance.review()
    assert decision.verdict is ReviewVerdict.INCONCLUSIVE
    assert codes(decision) == ("REVIEWER_UNAVAILABLE",)
    assert decision.human_review_required is True


def test_review_exceeding_the_declared_timeout_is_inconclusive(scenario):
    """48. The declarative timeout is a limit, not a suggestion."""
    request = scenario.request()
    late = F.response(request, completed_at=request.created_at + timedelta(
        seconds=scenario.config.review_timeout_seconds + 1))
    scenario.clock.advance(scenario.config.review_timeout_seconds + 2)
    decision = scenario.boundary.evaluate_response(request, late)
    assert decision.verdict is ReviewVerdict.INCONCLUSIVE
    assert "REVIEW_TIMEOUT_EXCEEDED" in codes(decision)


def test_response_from_the_future_or_too_old_blocks(scenario):
    """44/59. A response outside the live window is stale, never accepted."""
    request = scenario.request()
    future = F.response(request, completed_at=request.created_at + timedelta(seconds=10))
    assert "RESPONSE_STALE" in codes(scenario.boundary.evaluate_response(request, future))
    fresh = F.response(request)
    scenario.clock.advance(scenario.config.max_response_age_seconds + 1)
    assert "RESPONSE_STALE" in codes(scenario.boundary.evaluate_response(request, fresh))


# 49-54. Finding severity policy ------------------------------------------

@pytest.mark.parametrize("severity", [FindingSeverity.CRITICAL, FindingSeverity.HIGH,
                                      FindingSeverity.MEDIUM])
def test_remediation_required_finding_prevents_approval(scenario, severity):
    """49/50/51. CRITICAL, HIGH and MEDIUM remediation findings are fail-closed."""
    request = scenario.request()
    blocking = F.finding(finding_id="finding-0200", severity=severity,
                         reason_code="UNSAFE_BOUNDARY", remediation_required=True)
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.APPROVED, findings=(blocking,)))
    assert decision.verdict is not ReviewVerdict.APPROVED
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "VERDICT_FINDING_CONTRADICTION" in codes(decision)
    honest = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.CHANGES_REQUESTED,
                            findings=(blocking,)))
    assert honest.verdict is ReviewVerdict.CHANGES_REQUESTED
    assert honest.remediation_required is True


def test_medium_policy_can_be_narrowed_only_by_trusted_configuration():
    """51. The fail-closed MEDIUM rule is configuration, and it is documented."""
    instance = F.Scenario()
    assert instance.config.block_on_medium_remediation is True
    assert instance.config.blocking_severities() == (
        FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM)
    relaxed = instance.build_config(block_on_medium_remediation=False)
    assert relaxed.blocking_severities() == (FindingSeverity.CRITICAL, FindingSeverity.HIGH)


def test_changes_requested_requires_an_actionable_finding(scenario):
    """52. CHANGES_REQUESTED without a remediation finding is contradictory."""
    request = scenario.request()
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.CHANGES_REQUESTED, findings=()))
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "VERDICT_FINDING_CONTRADICTION" in codes(decision)
    advisory = F.finding(finding_id="finding-0300", remediation_required=False)
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.CHANGES_REQUESTED,
                            findings=(advisory,)))
    assert decision.verdict is ReviewVerdict.BLOCKED


@pytest.mark.parametrize("severity", [FindingSeverity.LOW, FindingSeverity.INFORMATIONAL])
def test_advisory_findings_may_coexist_with_approval(scenario, severity):
    """53/54. LOW and INFORMATIONAL findings are fine when nothing is required."""
    request = scenario.request()
    advisory = F.finding(finding_id="finding-0400", severity=severity,
                         reason_code="NAMING_SUGGESTION", remediation_required=False)
    decision = scenario.boundary.evaluate_response(
        request, F.response(request, verdict=ReviewVerdict.APPROVED, findings=(advisory,)))
    assert decision.verdict is ReviewVerdict.APPROVED
    assert decision.remediation_required is False
    assert decision.findings == (advisory,)


def test_findings_are_deterministically_sorted(scenario):
    """Finding policy. Order never depends on the reviewer's own ordering."""
    request = scenario.request()
    unsorted = (
        F.finding(finding_id="finding-0003", severity=FindingSeverity.INFORMATIONAL,
                  reason_code="NOTE_C", path=F.TEST_PATH, line=9),
        F.finding(finding_id="finding-0001", severity=FindingSeverity.LOW,
                  reason_code="NOTE_A", path=F.SOURCE_PATH, line=1),
        F.finding(finding_id="finding-0002", severity=FindingSeverity.LOW,
                  reason_code="NOTE_B", path=F.DOC_PATH, line=2),
    )
    first = scenario.boundary.evaluate_response(request, F.response(request, findings=unsorted))
    second = scenario.boundary.evaluate_response(
        request, F.response(request, findings=tuple(reversed(unsorted))))
    expected = ("finding-0002", "finding-0001", "finding-0003")
    assert tuple(f.finding_id for f in first.findings) == expected
    assert tuple(f.finding_id for f in second.findings) == expected
    assert first.findings == second.findings
    assert codes(first) == codes(second)


def test_blocked_and_inconclusive_decisions_carry_bounded_reason_codes(scenario):
    """Finding policy. Every code comes from the closed vocabulary."""
    request = scenario.request()
    for answer in (F.response(request, verdict=ReviewVerdict.BLOCKED),
                   F.response(request, verdict=ReviewVerdict.INCONCLUSIVE)):
        decision = scenario.boundary.evaluate_response(request, answer)
        assert decision.verdict in (ReviewVerdict.BLOCKED, ReviewVerdict.INCONCLUSIVE)
        assert codes(decision)
        assert set(codes(decision)) <= REASON_CODES


# 55-58. What approval is not ---------------------------------------------

def test_approval_is_never_human_authorization(scenario):
    """55. An APPROVED review leaves the human authority outstanding."""
    decision = scenario.review()
    assert decision.verdict is ReviewVerdict.APPROVED
    assert scenario.config.human_authorization_required is True
    assert decision.human_review_required is True
    assert decision.authorizes_execution is False
    assert decision.authority == DECISION_AUTHORITY
    assert "NOT_HUMAN_AUTHORIZATION" in decision.authority


def test_approval_cannot_reach_hitl_required_work():
    """55. HITL work is refused before the reviewer is ever asked."""
    instance = F.Scenario(outcome="HITL_REQUIRED")
    decision = instance.review()
    assert instance.reviewer.calls == []
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert codes(decision) == ("HUMAN_AUTHORIZATION_REQUIRED",)


def test_decision_has_no_completion_authority(scenario):
    """56. There is no field, method or code path that completes anything."""
    names = {item.name for item in fields(ReviewDecision)}
    assert not names & {"complete", "completed", "completion", "task_complete",
                        "project_complete", "approved_by_human"}
    assert not any("milestone" in name for name in names)
    api = {name for name in dir(IndependentReviewBoundary) if not name.startswith("_")}
    assert api == {"check_eligibility", "create_request", "review", "evaluate_response",
                   "remediation_request"}
    decision = scenario.review()
    assert decision.verdict is ReviewVerdict.APPROVED
    assert decision.authorizes_execution is False
    assert "NOT_COMPLETION" in decision.authority


def test_approval_cannot_modify_g4_state(scenario):
    """57. Recovery records are read-only inputs; nothing is written back."""
    before = (scenario.checkpoint.fingerprint(), scenario.assessment.fingerprint())
    decision = scenario.review()
    assert decision.verdict is ReviewVerdict.APPROVED
    assert (scenario.checkpoint.fingerprint(), scenario.assessment.fingerprint()) == before
    with pytest.raises(FrozenInstanceError):
        scenario.checkpoint.state = S.ABANDONED
    assert "RecoveryStore" not in SOURCE
    assert "open_recovery_store" not in SOURCE


def test_response_cannot_fabricate_file_or_test_evidence(scenario):
    """58. The response schema simply has no way to assert an observation."""
    response_names = {item.name for item in fields(ReviewResponse)}
    finding_names = {item.name for item in fields(ReviewFinding)}
    forbidden = {"changes", "created", "modified", "deleted", "tests", "verification_commands",
                 "exit_code", "stdout", "stderr", "evidence", "evidence_fingerprint",
                 "checkpoint_fingerprint", "state"}
    assert not response_names & forbidden
    assert not finding_names & forbidden
    request = scenario.request()
    decision = scenario.boundary.evaluate_response(request, F.response(request))
    assert decision.evidence_fingerprint == scenario.evidence.fingerprint()
    assert decision.checkpoint_fingerprint == scenario.checkpoint.fingerprint()


# 59-61. Replay and staleness ---------------------------------------------

def test_old_response_cannot_apply_to_new_evidence(scenario):
    """59. New G3 evidence is a new package, so an old answer no longer binds."""
    first = scenario.request()
    answer = F.response(first)
    scenario.evidence = scenario.build_evidence(tests=(F.verified_test("pytest-second"),))
    scenario.checkpoint = scenario.build_checkpoint(evidence=scenario.evidence)
    scenario.assessment = scenario.build_assessment(checkpoint=scenario.checkpoint)
    second = scenario.request()
    assert second.package.fingerprint() != first.package.fingerprint()
    decision = scenario.boundary.evaluate_response(second, answer)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "PACKAGE_FINGERPRINT_MISMATCH" in codes(decision)


@pytest.mark.parametrize("field_name,value", [
    ("task_id", "other-task"), ("execution_id", "other-attempt"),
    ("project_id", "other-project"), ("root", "/synthetic-other-root"),
])
def test_response_cannot_replay_across_task_execution_project_or_root(field_name, value):
    """60. Identity is inside the package, so a replay cannot survive it."""
    first = F.Scenario()
    request = first.request()
    answer = F.response(request)
    second = F.Scenario(**{field_name: value})
    other = second.request()
    assert other.package.fingerprint() != request.package.fingerprint()
    decision = second.boundary.evaluate_response(other, answer)
    assert decision.verdict is ReviewVerdict.BLOCKED
    assert "PACKAGE_FINGERPRINT_MISMATCH" in codes(decision)


def test_repeated_evaluation_of_one_response_is_idempotent(scenario):
    """61. The same immutable request and response give byte-identical results."""
    request = scenario.request()
    answer = F.response(request)
    first = scenario.boundary.evaluate_response(request, answer)
    second = scenario.boundary.evaluate_response(request, answer)
    assert first.canonical_json() == second.canonical_json()
    assert first.fingerprint() == second.fingerprint()
    assert first.decision_id == second.decision_id


def test_response_bound_to_another_configuration_blocks(scenario):
    """60. A request built under a different trusted configuration is refused."""
    other = F.Scenario()
    other.boundary = other.build_boundary(
        config=other.build_config(required_dimensions=(D.CORRECTNESS,)))
    foreign = other.request()
    with pytest.raises(ReviewError) as error:
        scenario.boundary.evaluate_response(foreign, F.response(foreign))
    assert error.value.code == "BINDING_INVALID"


# 62-64. The remediation boundary -----------------------------------------

def test_remediation_request_is_bounded_and_immutable():
    """62/64. G5 describes the next attempt. It never runs it."""
    instance = F.Scenario(reviewer=F.RecordingReviewer(F.changes_requested_response))
    decision = instance.review()
    assert decision.verdict is ReviewVerdict.CHANGES_REQUESTED
    remediation = instance.boundary.remediation_request(decision)
    assert type(remediation) is RemediationRequest
    assert remediation.project_id == F.PROJECT and remediation.task_id == F.TASK
    assert remediation.execution_id == F.EXECUTION
    assert remediation.review_id == decision.review_id
    assert remediation.previous_review_fingerprint == decision.response_fingerprint
    assert remediation.target_paths == (F.SOURCE_PATH,)
    assert remediation.finding_ids == ("finding-0100",)
    assert remediation.objectives == ("MISSING_INPUT_VALIDATION",)
    assert remediation.next_attempt == 2
    assert remediation.max_attempts == instance.config.max_review_attempts
    assert set(remediation.target_paths) <= set(instance.config.authorized_paths)
    with pytest.raises(FrozenInstanceError):
        remediation.next_attempt = 3
    assert len(instance.reviewer.calls) == 1
    assert instance.provider.requests == SELECTION_ORDER


def test_remediation_is_refused_for_any_other_verdict(scenario):
    """64. Only an actionable CHANGES_REQUESTED decision yields a remediation."""
    approved = scenario.review()
    with pytest.raises(ReviewError) as error:
        scenario.boundary.remediation_request(approved)
    assert error.value.code == "VERDICT_FINDING_CONTRADICTION"


def test_review_attempt_limit_is_enforced():
    """63. The bounded loop stops. G6 decides what happens after that."""
    instance = F.Scenario(reviewer=F.RecordingReviewer(F.changes_requested_response))
    instance.boundary = instance.build_boundary(
        config=instance.build_config(max_review_attempts=2))
    first = instance.review(attempt=1)
    assert instance.boundary.remediation_request(first).next_attempt == 2
    second = instance.review(attempt=2)
    with pytest.raises(ReviewError) as error:
        instance.boundary.remediation_request(second)
    assert error.value.code == "ATTEMPT_LIMIT_EXCEEDED"
    with pytest.raises(ReviewError):
        instance.review(attempt=3)


def test_g5_never_invokes_an_executor_a_runner_or_another_review():
    """64/65/66. There is no executor, adapter, runner or self-retry in G5."""
    instance = F.Scenario(reviewer=F.RecordingReviewer(F.changes_requested_response))
    decision = instance.review()
    instance.boundary.remediation_request(decision)
    assert len(instance.reviewer.calls) == 1
    for name in ("ProcessRunner", "ProcessInvocation", "ProcessOutcome", "StatelessAdapter",
                 "TrustedAdapterConfiguration", "execute_attempt", "IndependentVerifier",
                 "LocalWorkspaceObserver", "subprocess", "socket"):
        assert name not in SOURCE, name
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"run", "Popen", "call", "check_output", "spawn"}


# 69-71. Records, digests and honest claims -------------------------------

def test_every_record_is_immutable(scenario):
    """69. Nothing G5 emits can be edited after the fact."""
    request = scenario.request()
    answer = F.response(request)
    decision = scenario.boundary.evaluate_response(request, answer)
    samples = (scenario.config, scenario.channel, request, request.package,
               request.package.artifacts[0], answer, decision, F.finding(), F.SELECTION[0])
    for sample in samples:
        with pytest.raises(FrozenInstanceError):
            sample.schema_version = 99
    with pytest.raises(FrozenInstanceError):
        scenario.boundary.configuration = None


def test_fingerprints_are_deterministic_and_content_addressed(scenario):
    """70. Equal canonical payloads give equal digests, and nothing else does."""
    request = scenario.request()
    assert request.fingerprint() == request.fingerprint()
    assert request.package.fingerprint() == F.digest(request.package.canonical_json())
    answer = F.response(request)
    assert answer.fingerprint() == F.digest(answer.canonical_json())
    other = F.response(request, verdict=ReviewVerdict.INCONCLUSIVE)
    assert other.fingerprint() != answer.fingerprint()


def test_sha256_is_declared_non_authenticating(scenario):
    """71. Integrity digests are never presented as signatures or identity."""
    request = scenario.request()
    answer = F.response(request)
    decision = scenario.boundary.evaluate_response(request, answer)
    for record in (request, request.package, answer, decision):
        assert record.fingerprint_kind == "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"
    assert FINGERPRINT_KIND == "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"
    assert request.identity_kind.endswith("NOT_CRYPTOGRAPHICALLY_AUTHENTICATED")
    documentation = review_module.__doc__
    assert "not** signatures, authentication, non-repudiation or\n  replay protection" in documentation
    assert "Durable replay prevention is deferred" in documentation


def test_error_and_reason_codes_are_a_closed_bounded_vocabulary():
    """Error safety. Fixed codes only; no path, prose or provider text anywhere."""
    assert review_module.ERROR_CODES is REASON_CODES
    for code in REASON_CODES:
        assert code.isupper() and code.replace("_", "").isalnum() and len(code) <= 48
    error = ReviewError("not-a-real-code")
    assert error.code == "CONFIGURATION_INVALID"
    assert str(error) == "CONFIGURATION_INVALID"


def test_parse_review_response_is_the_only_decoder():
    """36/46. Structured decode only; no alternative permissive path exists."""
    with pytest.raises(ReviewError) as error:
        parse_review_response("APPROVED")
    assert error.value.code == "RESPONSE_MALFORMED"
    with pytest.raises(ReviewError) as error:
        parse_review_response({"verdict": "APPROVED"})
    assert error.value.code == "RESPONSE_SCHEMA_INVALID"
