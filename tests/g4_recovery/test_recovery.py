"""Isolated G4 checks: temporary directories and throwaway databases only.

Nothing here reads, writes or inspects a ZERO runtime, data or checkpoint path.
Every store lives under pytest's ``tmp_path``. Crash coverage kills a real writer
subprocess; that proves process-termination atomicity, not power-loss durability.

Requirements 61-64 (the existing G1, G2A, G2B and G3 suites still pass) are
proven by running those four suites separately, not from inside this module.
"""

import ast
import contextlib
import importlib.util
import inspect
import json
import sqlite3
import subprocess
import sys
import threading
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zero_core.engineering_contracts import (
    EngineeringExecutionResult, OperationRule, RequestedOperation, TaskPacket, WorkspacePolicy,
)
from zero_core.engineering_verification import (
    Binding, ChangeObservation, VerificationEvidence, VerificationVerdict,
)
import zero_core.engineering_recovery as recovery
from zero_core.engineering_recovery import (
    DurabilityMode, LEGAL_TRANSITIONS, RECOVERY_DECISIONS, RecoveryAction, RecoveryCheckpoint,
    RecoveryError, RecoveryEvent, RecoveryState, RetentionPolicy, TrustedRecoveryConfiguration,
    open_recovery_store,
)


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)
S = RecoveryState
A = RecoveryAction
V = VerificationVerdict
PROJECT = "project"
TASK = "task"
EXECUTION = "attempt"

MODULE_PATH = Path(recovery.__file__).resolve()
SOURCE = MODULE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
TEST_ROOT = Path(__file__).resolve().parent
FIXTURE = TEST_ROOT / "fixtures" / "recovery_writer.py"
REPOSITORY_ROOT = TEST_ROOT.parents[1]

SECRET_SUMMARY = "PROMPTMARKER-executor-said-149-tests-passed-AKIAZZZ"
SECRET_FILE_TEXT = "FILECONTENTMARKER-do-not-persist-me"
SECRET_ENVIRONMENT = "ENVIRONMENTMARKER-do-not-persist-me"
SECRET_STDOUT = "STDOUTMARKER-do-not-persist-me"

EVIDENCE_REASONS = {
    V.VERIFIED: ("OBSERVED_REQUIREMENTS_MET",),
    V.FAILED: ("EXPECTED_CHANGE_MISSING",),
    V.BLOCKED: ("OBSERVATION_BLOCKED",),
    V.INCONCLUSIVE: ("OBSERVATION_UNCERTAIN",),
}
STATE_VERDICTS = {state: verdict for verdict, state in recovery.VERDICT_STATES.items()}

# Shortest legal path from an empty chain to each reachable durable state.
TERMINAL_PATH = (S.PLANNED, S.EXECUTION_STARTED, S.EXECUTION_REPORTED, S.VERIFICATION_STARTED)
PATHS = {
    S.PLANNED: (S.PLANNED,),
    S.EXECUTION_STARTED: (S.PLANNED, S.EXECUTION_STARTED),
    S.EXECUTION_REPORTED: (S.PLANNED, S.EXECUTION_STARTED, S.EXECUTION_REPORTED),
    S.VERIFICATION_STARTED: TERMINAL_PATH,
    S.VERIFIED: TERMINAL_PATH + (S.VERIFIED,),
    S.FAILED: TERMINAL_PATH + (S.FAILED,),
    S.BLOCKED: TERMINAL_PATH + (S.BLOCKED,),
    S.INCONCLUSIVE: TERMINAL_PATH + (S.INCONCLUSIVE,),
    S.INTERRUPTED: (S.PLANNED, S.EXECUTION_STARTED, S.INTERRUPTED),
    S.REQUIRES_REVERIFICATION: (S.PLANNED, S.EXECUTION_STARTED, S.EXECUTION_REPORTED,
                                S.REQUIRES_REVERIFICATION),
    S.ABANDONED: (S.PLANNED, S.ABANDONED),
}


def load_fixture():
    specification = importlib.util.spec_from_file_location("g4_recovery_writer", FIXTURE)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def table_names(database):
    connection = sqlite3.connect(str(database))
    try:
        return sorted(row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"))
    finally:
        connection.close()


class FakeClock:
    def __init__(self, start=NOW):
        self.value = start

    def now(self):
        return self.value


class Counter:
    def __init__(self, prefix="id"):
        self.prefix = prefix
        self.count = 0

    def next_id(self):
        self.count += 1
        return "%s-%04d" % (self.prefix, self.count)


class FixedIdentifiers:
    def __init__(self, values):
        self.values = list(values)

    def next_id(self):
        return self.values.pop(0)


class Scenario:
    """One temporary repository, one temporary recovery store, one attempt."""

    def __init__(self, tmp_path, **configuration):
        self.base = tmp_path
        self.root = tmp_path / "repo"
        self.root.mkdir()
        (self.root / "a.txt").write_text(SECRET_FILE_TEXT, encoding="utf-8")
        self.directory = tmp_path / "recovery"
        self.directory.mkdir()
        self.database = self.directory / "recovery.sqlite3"
        self.clock = FakeClock()
        self.stores = 0
        self.keys = 0
        self.expected = None
        self.config = TrustedRecoveryConfiguration(
            project_id=PROJECT, repository_root=self.root.resolve().as_posix(),
            recovery_directory=self.directory.resolve().as_posix(),
            database_path=self.database.as_posix(), **configuration)
        operation = RequestedOperation(action="CREATE_FILE", target="a.txt")
        self.packet = TaskPacket(
            packet_id="packet", project_id=PROJECT, task_id=TASK, milestone_id="milestone",
            repository_root=self.config.repository_root, policy_id="policy", policy_version=1,
            context_fingerprint="a" * 64, operations=(operation,), created_at=NOW)
        self.policy = WorkspacePolicy(
            policy_id="policy", policy_version=1, project_id=PROJECT,
            repository_root=self.config.repository_root,
            rules=(OperationRule(operation=operation, outcome="LOW_RISK"),))
        self.decision = self.policy.evaluate(self.packet, decision_id="decision", evaluated_at=NOW)
        self.attempt = EngineeringExecutionResult(
            execution_id=EXECUTION, executor_id="untrusted-worker", project_id=PROJECT, task_id=TASK,
            packet_fingerprint=self.packet.fingerprint(), permission_decision_id="decision",
            status="SUCCESS", started_at=NOW, finished_at=NOW + timedelta(seconds=1),
            summary=SECRET_SUMMARY)
        self.store = self.open()

    def open(self, configuration=None, clock=None, ids=None):
        self.stores += 1
        return open_recovery_store(configuration or self.config, clock=clock or self.clock,
                                   id_source=ids or Counter("s%d" % self.stores))

    def evidence(self, verdict=V.VERIFIED, execution_id=EXECUTION, task_id=TASK):
        binding = Binding(PROJECT, task_id, execution_id, self.config.repository_root,
                          self.packet.fingerprint(), self.policy.fingerprint(),
                          self.decision.fingerprint(), "b" * 64)
        return VerificationEvidence(binding, self.attempt.fingerprint(), "c" * 64, "d" * 64,
                                    ChangeObservation(), (), verdict, EVIDENCE_REASONS[verdict], NOW)

    def key(self):
        self.keys += 1
        return "key-%04d" % self.keys

    def append(self, to_state, *, store=None, expected=Ellipsis, key=None, task_id=TASK,
               execution_id=EXECUTION, packet=None, policy=None, decision=None, **kwargs):
        checkpoint = (store or self.store).append(
            task_id=task_id, execution_id=execution_id, to_state=to_state,
            expected_checkpoint_fingerprint=self.expected if expected is Ellipsis else expected,
            idempotency_key=key or self.key(), packet=packet if packet is not None else self.packet,
            policy=policy if policy is not None else self.policy,
            decision=decision if decision is not None else self.decision, **kwargs)
        self.expected = checkpoint.fingerprint()
        return checkpoint

    def step(self, state, **kwargs):
        if state in recovery.ATTEMPT_REQUIRED_STATES:
            kwargs.setdefault("attempt", self.attempt)
        if state in recovery.EVIDENCE_REQUIRED_STATES:
            kwargs.setdefault("evidence", self.evidence(STATE_VERDICTS[state]))
        return self.append(state, **kwargs)

    def advance(self, *states):
        for state in states:
            self.step(state)
        return self

    def reach(self, state):
        return self.advance(*PATHS[state])

    def assess(self, store=None):
        return (store or self.store).assess(task_id=TASK, execution_id=EXECUTION)

    def restart(self):
        self.store.close()
        self.store = self.open()
        return self.store

    def raw_connection(self):
        connection = sqlite3.connect(str(self.database), isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextlib.contextmanager
    def raw(self):
        connection = self.raw_connection()
        try:
            yield connection
        finally:
            connection.close()

    def payload(self, table, sequence):
        with self.raw() as connection:
            return json.loads(connection.execute(
                "SELECT payload FROM %s WHERE sequence = ?" % table, (sequence,)).fetchone()[0])

    def counts(self):
        with self.raw() as connection:
            return (connection.execute("SELECT COUNT(*) FROM recovery_checkpoint").fetchone()[0],
                    connection.execute("SELECT COUNT(*) FROM recovery_event").fetchone()[0])


@pytest.fixture
def scenario(tmp_path):
    instance = Scenario(tmp_path)
    yield instance
    instance.store.close()


def tamper(scenario, table, column, value, sequence=1):
    """Rewrite one stored column behind the store's back, then reopen."""
    scenario.store.close()
    with scenario.raw() as connection:
        connection.execute("UPDATE %s SET %s = ? WHERE sequence = ?" % (table, column),
                           (value, sequence))
    scenario.store = scenario.open()


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# 1. Import is inert -------------------------------------------------------

def test_fresh_import_is_inert(tmp_path):
    """1. Importing G4 opens nothing, writes nothing and connects to nothing."""
    script = r'''
import sys, os
sys.path.insert(0, sys.argv[1])
import zero_core.engineering_contracts, zero_core.engineering_execution
import zero_core.engineering_verification, sqlite3, json, hashlib, re, stat


class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"requests", "httpx", "urllib", "socket", "subprocess",
                                      "multiprocessing", "pickle"}:
            raise AssertionError("forbidden import: " + fullname)
        if fullname.startswith("zero_core.") and fullname not in {
                "zero_core.engineering_recovery", "zero_core.engineering_contracts",
                "zero_core.engineering_execution", "zero_core.engineering_verification"}:
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
import zero_core.engineering_recovery
assert "zero_core.process_runner" not in sys.modules
print("INERT")
'''
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    completed = subprocess.run([sys.executable, "-B", "-c", script, str(REPOSITORY_ROOT)],
                               cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "INERT"
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")) == before


def test_module_never_reads_the_environment():
    """1. No environment access exists anywhere, not only at import time."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "environb", "getenv", "putenv", "unsetenv"}
        if isinstance(node, ast.Name):
            assert node.id not in {"environ", "getenv", "putenv"}


def test_module_imports_no_execution_or_network_capability():
    """57/58/59/60. No runner, adapter, verifier, subprocess, network or milestone."""
    allowed = {"zero_core.engineering_contracts", "zero_core.engineering_execution",
               "zero_core.engineering_verification"}
    banned_roots = {"subprocess", "socket", "requests", "httpx", "urllib", "multiprocessing",
                    "asyncio", "pickle", "yaml", "shutil", "ctypes", "threading", "importlib"}
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned_roots
                assert not alias.name.startswith("zero_core.") or alias.name in allowed
        if isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] not in banned_roots
            assert not node.module.startswith("zero_core.") or node.module in allowed
    banned_names = {"ProcessRunner", "LocalProcessRunner", "IndependentVerifier", "StatelessAdapter",
                    "LocalWorkspaceObserver", "execute_attempt", "Popen", "system", "eval", "exec",
                    "compile", "__import__", "pickle"}
    for node in ast.walk(TREE):
        if isinstance(node, (ast.Name, ast.Attribute)):
            label = node.id if isinstance(node, ast.Name) else node.attr
            assert label not in banned_names, label
            assert "milestone" not in label.lower(), label
            assert not any(agent in label.lower() for agent in ("codex", "goose", "claude")), label


def test_only_constant_sql_reaches_the_driver():
    """47. Every statement is a literal or module constant; values are bound."""
    constants = {target.id for node in TREE.body if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name) and target.id.isupper()}
    calls = [node for node in ast.walk(TREE) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr in ("execute", "executemany", "executescript")]
    assert len(calls) >= 10
    for call in calls:
        assert call.func.attr == "execute"
        first = call.args[0]
        assert (isinstance(first, ast.Constant) and isinstance(first.value, str)) or (
            isinstance(first, ast.Name) and first.id in constants), ast.dump(first)
        assert len(call.args) <= 2
        if len(call.args) == 2:
            assert isinstance(call.args[1], (ast.Name, ast.Tuple, ast.BinOp))


# 2-10. Trusted store location and schema ----------------------------------

def test_store_is_created_only_on_explicit_open(tmp_path):
    """2. Nothing on disk changes until open_recovery_store is called."""
    root = tmp_path / "repo"
    root.mkdir()
    directory = tmp_path / "recovery"
    directory.mkdir()
    database = directory / "recovery.sqlite3"
    configuration = TrustedRecoveryConfiguration(
        project_id=PROJECT, repository_root=root.resolve().as_posix(),
        recovery_directory=directory.resolve().as_posix(), database_path=database.as_posix())
    assert not database.exists()
    assert list(directory.iterdir()) == []
    store = open_recovery_store(configuration, clock=FakeClock(), id_source=Counter())
    try:
        assert database.exists()
        assert table_names(database) == sorted(recovery.TABLES)
    finally:
        store.close()


def test_database_location_is_not_task_controlled(scenario):
    """3. No caller, packet or executor value can select the store location."""
    for function in (open_recovery_store, recovery.RecoveryStore.append,
                     recovery.RecoveryStore.assess, recovery.RecoveryStore.latest_checkpoint):
        names = set(inspect.signature(function).parameters)
        assert not {"path", "database", "database_path", "directory", "filename", "uri"} & names
    hostile_root = scenario.base / "hostile"
    hostile_root.mkdir()
    hostile = scenario.packet.model_copy(update={"repository_root": hostile_root.resolve().as_posix()})
    with pytest.raises(RecoveryError) as error:
        scenario.store.append(task_id=TASK, execution_id=EXECUTION, to_state=S.PLANNED,
                              expected_checkpoint_fingerprint=None, idempotency_key="k",
                              packet=hostile, policy=scenario.policy, decision=scenario.decision)
    assert error.value.code == "BINDING_INVALID"
    assert scenario.config.database_path == scenario.database.resolve().as_posix()
    assert list(hostile_root.iterdir()) == []


def test_database_outside_trusted_directory_blocks(tmp_path):
    """4. The database must live inside the explicitly trusted recovery directory."""
    root = tmp_path / "repo"
    root.mkdir()
    directory = tmp_path / "recovery"
    directory.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    for candidate in (outside / "recovery.sqlite3", tmp_path / "recovery.sqlite3"):
        with pytest.raises(RecoveryError) as error:
            TrustedRecoveryConfiguration(
                project_id=PROJECT, repository_root=root.resolve().as_posix(),
                recovery_directory=directory.resolve().as_posix(),
                database_path=candidate.as_posix())
        assert error.value.code == "UNTRUSTED_PATH"


def test_link_or_reparse_ambiguity_blocks(tmp_path):
    """5. A symlink, junction or reparse point is rejected, never followed."""
    root = tmp_path / "repo"
    root.mkdir()
    directory = tmp_path / "recovery"
    directory.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(directory, target_is_directory=True)
        (tmp_path / "real.sqlite3").write_bytes(b"")
        (directory / "r.sqlite3").symlink_to(tmp_path / "real.sqlite3")
    except (OSError, NotImplementedError):
        pytest.skip("this host does not permit unprivileged link creation")
    with pytest.raises(RecoveryError) as error:
        TrustedRecoveryConfiguration(
            project_id=PROJECT, repository_root=root.resolve().as_posix(),
            recovery_directory=linked.as_posix(), database_path=(linked / "r.sqlite3").as_posix())
    assert error.value.code == "UNTRUSTED_PATH"
    with pytest.raises(RecoveryError) as error:
        TrustedRecoveryConfiguration(
            project_id=PROJECT, repository_root=root.resolve().as_posix(),
            recovery_directory=directory.resolve().as_posix(),
            database_path=(directory / "r.sqlite3").as_posix())
    assert error.value.code == "UNTRUSTED_PATH"


def test_missing_or_noncanonical_root_blocks(tmp_path):
    """6. The repository root must exist and be canonical."""
    directory = tmp_path / "recovery"
    directory.mkdir()
    (tmp_path / "repo").mkdir()
    database = (directory / "r.sqlite3").as_posix()
    for candidate in ((tmp_path / "missing").as_posix(),
                      (tmp_path / "repo" / ".." / "repo").as_posix(), "relative/path", ""):
        with pytest.raises(RecoveryError) as error:
            TrustedRecoveryConfiguration(
                project_id=PROJECT, repository_root=candidate,
                recovery_directory=directory.resolve().as_posix(), database_path=database)
        assert error.value.code in ("UNTRUSTED_PATH", "INVALID_CONFIGURATION")


def test_initial_schema_creation_is_atomic(tmp_path, monkeypatch):
    """7. An interrupted first open leaves no partial schema behind."""
    root = tmp_path / "repo"
    root.mkdir()
    directory = tmp_path / "recovery"
    directory.mkdir()
    database = directory / "r.sqlite3"
    configuration = TrustedRecoveryConfiguration(
        project_id=PROJECT, repository_root=root.resolve().as_posix(),
        recovery_directory=directory.resolve().as_posix(), database_path=database.as_posix())
    monkeypatch.setattr(recovery, "CREATE_EVENT_TABLE", "CREATE TABLE broken (")
    with pytest.raises(RecoveryError) as error:
        open_recovery_store(configuration, clock=FakeClock(), id_source=Counter())
    assert error.value.code == "STORE_UNAVAILABLE"
    assert table_names(database) == []
    monkeypatch.undo()
    store = open_recovery_store(configuration, clock=FakeClock(), id_source=Counter())
    try:
        assert table_names(database) == sorted(recovery.TABLES)
    finally:
        store.close()


def test_reopening_the_same_schema_succeeds(scenario):
    """8. A supported existing schema is reused, never recreated or migrated."""
    scenario.reach(S.PLANNED)
    scenario.restart()
    assert scenario.assess().state is S.PLANNED
    with scenario.raw() as connection:
        assert connection.execute("SELECT COUNT(*) FROM recovery_schema").fetchone()[0] == 1
        assert connection.execute("SELECT schema_version FROM recovery_schema").fetchone()[0] == 1


def test_unknown_newer_schema_blocks(scenario):
    """9. A newer or unknown schema version fails closed without migration."""
    scenario.store.close()
    with scenario.raw() as connection:
        connection.execute("UPDATE recovery_schema SET schema_version = 2")
    with pytest.raises(RecoveryError) as error:
        scenario.open()
    assert error.value.code == "SCHEMA_UNSUPPORTED"
    with scenario.raw() as connection:
        assert connection.execute("SELECT schema_version FROM recovery_schema").fetchone()[0] == 2


def test_malformed_schema_blocks(scenario, tmp_path):
    """10. An unexpected table or an incomplete schema fails closed."""
    scenario.store.close()
    with scenario.raw() as connection:
        connection.execute("CREATE TABLE unexpected (id INTEGER)")
    with pytest.raises(RecoveryError) as error:
        scenario.open()
    assert error.value.code == "SCHEMA_CORRUPT"
    other = tmp_path / "second"
    other.mkdir()
    partial = other / "partial.sqlite3"
    connection = sqlite3.connect(str(partial), isolation_level=None)
    try:
        connection.execute(recovery.CREATE_SCHEMA_TABLE)
    finally:
        connection.close()
    configuration = TrustedRecoveryConfiguration(
        project_id=PROJECT, repository_root=scenario.config.repository_root,
        recovery_directory=other.resolve().as_posix(), database_path=partial.as_posix())
    with pytest.raises(RecoveryError) as error:
        open_recovery_store(configuration, clock=FakeClock(), id_source=Counter())
    assert error.value.code == "SCHEMA_CORRUPT"


# 11-13. Atomic transitions ------------------------------------------------

def test_legal_transition_commits_checkpoint_and_event(scenario):
    """11. One legal transition writes exactly one checkpoint and one event."""
    first = scenario.step(S.PLANNED)
    assert scenario.counts() == (1, 1)
    second = scenario.step(S.EXECUTION_STARTED)
    assert scenario.counts() == (2, 2)
    assert second.previous_checkpoint_fingerprint == first.fingerprint()
    with scenario.raw() as connection:
        rows = connection.execute(
            "SELECT sequence, checkpoint_id FROM recovery_event ORDER BY sequence").fetchall()
    assert [row[0] for row in rows] == [1, 2]
    assert [row[1] for row in rows] == [first.checkpoint_id, second.checkpoint_id]


def test_failed_transition_writes_neither_record(scenario):
    """12/34. A rejected transition rolls back; the previous state is intact."""
    scenario.step(S.PLANNED)
    before = scenario.counts()
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.VERIFICATION_STARTED, attempt=scenario.attempt)
    assert error.value.code == "ILLEGAL_TRANSITION"
    assert scenario.counts() == before
    assert scenario.store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION).state is S.PLANNED


def test_reader_never_observes_half_a_transition(scenario):
    """13. A concurrent reader sees the complete old state, never a lone checkpoint."""
    scenario.step(S.PLANNED)
    ready, paused, released = threading.Event(), threading.Event(), threading.Event()
    observed = []

    def reader():
        store = scenario.open(ids=Counter("reader"))
        ready.set()
        try:
            if paused.wait(60):
                try:
                    latest = store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
                    observed.append((latest.state, latest.sequence))
                except RecoveryError as error:
                    observed.append(error.code)
        finally:
            released.set()
            store.close()

    def trace(statement):
        if str(statement).lstrip().upper().startswith("INSERT INTO RECOVERY_EVENT"):
            paused.set()
            released.wait(60)

    thread = threading.Thread(target=reader)
    thread.start()
    assert ready.wait(60)
    scenario.store._connection.set_trace_callback(trace)
    try:
        scenario.step(S.EXECUTION_STARTED)
    finally:
        scenario.store._connection.set_trace_callback(None)
        released.set()
        thread.join(90)
    assert observed and observed[0] in ((S.PLANNED, 1), "STORE_BUSY")
    assert scenario.counts() == (2, 2)


# 14-22. Restart and verification authority --------------------------------

@pytest.mark.parametrize("state,expected_state,action,reverify", [
    (S.PLANNED, S.PLANNED, A.RESUME_PLANNING, False),
    (S.EXECUTION_STARTED, S.INTERRUPTED, A.REVERIFY_WORKSPACE, True),
    (S.EXECUTION_REPORTED, S.REQUIRES_REVERIFICATION, A.REVERIFY_WORKSPACE, True),
    (S.VERIFICATION_STARTED, S.INTERRUPTED, A.REVERIFY_WORKSPACE, True),
])
def test_interrupted_states_reload_requiring_reverification(
        tmp_path, state, expected_state, action, reverify):
    """14/15/16/17. Restart never assumes an interrupted executor finished."""
    scenario = Scenario(tmp_path)
    try:
        scenario.reach(state)
        scenario.restart()
        assessment = scenario.assess()
        assert assessment.chain_valid is True
        assert assessment.last_valid_checkpoint.state is state
        assert assessment.state is expected_state
        assert assessment.action is action
        assert assessment.reverification_required is reverify
    finally:
        scenario.store.close()


def test_verified_survives_restart_only_with_bound_evidence(scenario):
    """18. VERIFIED persists only while its chain and evidence binding validate."""
    scenario.reach(S.VERIFIED)
    checkpoint = scenario.store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
    assert checkpoint.evidence_fingerprint == scenario.evidence(V.VERIFIED).fingerprint()
    scenario.restart()
    assessment = scenario.assess()
    assert (assessment.state, assessment.action, assessment.reverification_required) == (
        S.VERIFIED, A.NO_ACTION, False)
    payload = scenario.payload("recovery_checkpoint", 5)
    payload["evidence_fingerprint"] = "e" * 64
    tamper(scenario, "recovery_checkpoint", "payload", canonical(payload), sequence=5)
    blocked = scenario.assess()
    assert blocked.chain_valid is False
    assert blocked.action is A.BLOCK_CORRUPT_STATE
    assert blocked.state is None and blocked.last_valid_checkpoint is None


def test_executor_success_alone_cannot_become_verified(scenario):
    """19. An executor SUCCESS claim never creates a durable VERIFIED state."""
    scenario.advance(*TERMINAL_PATH)
    assert scenario.attempt.status == "SUCCESS"
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.VERIFIED, attempt=scenario.attempt)
    assert error.value.code == "EVIDENCE_REQUIRED"
    for verdict in (V.FAILED, V.BLOCKED, V.INCONCLUSIVE):
        with pytest.raises(RecoveryError) as error:
            scenario.append(S.VERIFIED, attempt=scenario.attempt, evidence=scenario.evidence(verdict))
        assert error.value.code == "EVIDENCE_REQUIRED"
    assert scenario.counts() == (4, 4)


@pytest.mark.parametrize("verdict,state", [
    (V.FAILED, S.FAILED), (V.BLOCKED, S.BLOCKED), (V.INCONCLUSIVE, S.INCONCLUSIVE),
])
def test_g3_verdicts_persist_as_their_recovery_state(tmp_path, verdict, state):
    """20/21/22. A G3 FAILED, BLOCKED or INCONCLUSIVE verdict maps exactly."""
    scenario = Scenario(tmp_path)
    try:
        scenario.reach(state)
        scenario.restart()
        assessment = scenario.assess()
        assert assessment.last_valid_checkpoint.state is state
        assert assessment.state is state
        assert assessment.reverification_required is True
        assert assessment.last_valid_checkpoint.evidence_fingerprint == \
            scenario.evidence(verdict).fingerprint()
    finally:
        scenario.store.close()


# 23-29. Transition and identity rejection ---------------------------------

def test_illegal_transition_blocks(scenario):
    """23. An edge outside the documented graph is rejected."""
    scenario.reach(S.VERIFIED)
    for state in (S.EXECUTION_STARTED, S.PLANNED, S.EXECUTION_REPORTED):
        with pytest.raises(RecoveryError) as error:
            scenario.append(state, **({"attempt": scenario.attempt}
                                      if state is S.EXECUTION_REPORTED else {}))
        assert error.value.code == "ILLEGAL_TRANSITION"
    assert scenario.counts() == (5, 5)


def test_skipped_state_blocks(scenario):
    """24. VERIFICATION_STARTED cannot be skipped on the way to a verdict."""
    scenario.advance(S.PLANNED, S.EXECUTION_STARTED, S.EXECUTION_REPORTED)
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.VERIFIED, attempt=scenario.attempt, evidence=scenario.evidence())
    assert error.value.code == "ILLEGAL_TRANSITION"
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.EXECUTION_REPORTED, expected=None, attempt=scenario.attempt)
    assert error.value.code == "STALE_STATE"
    assert scenario.counts() == (3, 3)


def test_stale_expected_fingerprint_blocks(scenario):
    """25. A stale compare-and-swap token never overwrites newer state."""
    first = scenario.step(S.PLANNED)
    scenario.step(S.EXECUTION_STARTED)
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.EXECUTION_STARTED, expected=first.fingerprint())
    assert error.value.code == "STALE_STATE"
    assert scenario.counts() == (2, 2)


def test_sequence_reuse_or_decrease_blocks(scenario):
    """26. Sequence numbers are store-assigned, contiguous and never reused."""
    scenario.advance(S.PLANNED, S.EXECUTION_STARTED)
    with scenario.raw() as connection:
        row = connection.execute(
            "SELECT checkpoint_id, project_id, task_id, execution_id, payload, fingerprint,"
            " previous_fingerprint, request_digest, idempotency_key FROM recovery_checkpoint"
            " WHERE sequence = 2").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO recovery_checkpoint (checkpoint_id, project_id, task_id, execution_id,"
                " sequence, payload, fingerprint, previous_fingerprint, request_digest,"
                " idempotency_key) VALUES (?, ?, ?, ?, 2, ?, ?, ?, ?, ?)",
                ("other",) + row[1:4] + row[4:5] + ("f" * 64,) + row[6:8] + ("otherkey",))
    assert scenario.counts() == (2, 2)
    assert [c.sequence for c in (scenario.store.latest_checkpoint(
        task_id=TASK, execution_id=EXECUTION),)] == [2]


def test_identity_rebinding_blocks(scenario, tmp_path):
    """27. Project, task, execution and root bindings are fixed for a chain."""
    scenario.step(S.PLANNED)
    other_packet = scenario.packet.model_copy(update={"task_id": "othertask"})
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.EXECUTION_STARTED, task_id="othertask", packet=other_packet)
    assert error.value.code == "BINDING_INVALID"
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.EXECUTION_REPORTED,
                        attempt=scenario.attempt.model_copy(update={"execution_id": "other"}))
    assert error.value.code == "BINDING_INVALID"
    second_root = tmp_path / "second-repo"
    second_root.mkdir()
    rebound = TrustedRecoveryConfiguration(
        project_id=PROJECT, repository_root=second_root.resolve().as_posix(),
        recovery_directory=scenario.config.recovery_directory,
        database_path=scenario.config.database_path)
    store = scenario.open(configuration=rebound)
    try:
        with pytest.raises(RecoveryError) as error:
            store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
        assert error.value.code == "BINDING_INVALID"
        assert store.assess(task_id=TASK, execution_id=EXECUTION).action is A.BLOCK_CORRUPT_STATE
    finally:
        store.close()
    assert scenario.counts() == (1, 1)


def test_duplicate_checkpoint_identifier_blocks(scenario):
    """28. A repeated checkpoint ID is refused and writes nothing."""
    store = scenario.open(ids=FixedIdentifiers(["same", "event-1", "same", "event-2"]))
    try:
        scenario.append(S.PLANNED, store=store)
        with pytest.raises(RecoveryError) as error:
            scenario.append(S.EXECUTION_STARTED, store=store)
        assert error.value.code == "DUPLICATE_RECORD"
    finally:
        store.close()
    assert scenario.counts() == (1, 1)


def test_duplicate_event_identifier_blocks(scenario):
    """29/34. A repeated event ID rolls the whole transition back."""
    store = scenario.open(ids=FixedIdentifiers(["cp-1", "ev-1", "cp-2", "ev-1"]))
    try:
        scenario.append(S.PLANNED, store=store)
        with pytest.raises(RecoveryError) as error:
            scenario.append(S.EXECUTION_STARTED, store=store)
        assert error.value.code == "DUPLICATE_RECORD"
        assert store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION).state is S.PLANNED
    finally:
        store.close()
    assert scenario.counts() == (1, 1)


# 30-34. Idempotency, concurrency and rollback -----------------------------

def test_exact_idempotent_retry_produces_no_duplicate(scenario):
    """30. Repeating the identical request returns the stored record."""
    first = scenario.append(S.PLANNED, key="retry")
    scenario.expected = None
    second = scenario.append(S.PLANNED, key="retry")
    assert second.fingerprint() == first.fingerprint()
    assert second.checkpoint_id == first.checkpoint_id
    assert scenario.counts() == (1, 1)


def test_conflicting_idempotency_reuse_blocks(scenario):
    """31. The same key with different content is refused, never merged."""
    scenario.append(S.PLANNED, key="retry")
    scenario.expected = None
    with pytest.raises(RecoveryError) as error:
        scenario.append(S.PLANNED, key="retry", reason_codes=("OPERATOR_DECISION",))
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert scenario.counts() == (1, 1)


def test_concurrent_writers_cannot_overwrite_each_other(scenario):
    """32. Two writers observing the same state cannot both advance it."""
    scenario.step(S.PLANNED)
    first = scenario.open(ids=Counter("w1"))
    second = scenario.open(ids=Counter("w2"))
    try:
        shared = first.latest_checkpoint(task_id=TASK, execution_id=EXECUTION).fingerprint()
        assert second.latest_checkpoint(task_id=TASK, execution_id=EXECUTION).fingerprint() == shared
        scenario.append(S.EXECUTION_STARTED, store=first, expected=shared, key="writer-one")
        with pytest.raises(RecoveryError) as error:
            scenario.append(S.EXECUTION_STARTED, store=second, expected=shared, key="writer-two")
        assert error.value.code == "STALE_STATE"
        assert second.latest_checkpoint(
            task_id=TASK, execution_id=EXECUTION).checkpoint_id.startswith("w1-")
    finally:
        first.close()
        second.close()
    assert scenario.counts() == (2, 2)


def test_busy_database_fails_with_a_bounded_code(tmp_path):
    """33. Contention yields a sanitized STORE_BUSY, never a driver message."""
    scenario = Scenario(tmp_path, busy_timeout_ms=100)
    blocker = scenario.raw_connection()
    try:
        blocker.execute("BEGIN EXCLUSIVE")
        with pytest.raises(RecoveryError) as error:
            scenario.step(S.PLANNED)
        assert error.value.code == "STORE_BUSY"
        assert str(error.value) == "STORE_BUSY"
        assert scenario.database.name not in str(error.value)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
        scenario.store.close()


# 35-44. Append-only integrity --------------------------------------------

def test_modified_checkpoint_payload_is_detected(scenario):
    """35. A rewritten checkpoint payload no longer matches its stored digest."""
    scenario.reach(S.EXECUTION_STARTED)
    payload = scenario.payload("recovery_checkpoint", 1)
    payload["reason_codes"] = ["OPERATOR_DECISION"]
    tamper(scenario, "recovery_checkpoint", "payload", canonical(payload))
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_modified_event_payload_is_detected(scenario):
    """36. A rewritten event payload is detected on load."""
    scenario.reach(S.EXECUTION_STARTED)
    payload = scenario.payload("recovery_event", 2)
    payload["reason_codes"] = ["OPERATOR_DECISION"]
    tamper(scenario, "recovery_event", "payload", canonical(payload), sequence=2)
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_broken_checkpoint_chain_is_detected(scenario):
    """37. A broken previous-checkpoint pointer blocks."""
    scenario.reach(S.EXECUTION_STARTED)
    tamper(scenario, "recovery_checkpoint", "previous_fingerprint", "f" * 64, sequence=2)
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_broken_event_chain_is_detected(scenario):
    """38. A broken previous-event pointer blocks."""
    scenario.reach(S.EXECUTION_STARTED)
    tamper(scenario, "recovery_event", "previous_fingerprint", "f" * 64, sequence=2)
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_deleted_middle_record_is_detected(scenario):
    """39. A removed record leaves a sequence gap that blocks."""
    scenario.reach(S.EXECUTION_REPORTED)
    scenario.store.close()
    with scenario.raw() as connection:
        connection.execute("DELETE FROM recovery_event WHERE sequence = 2")
        connection.execute("DELETE FROM recovery_checkpoint WHERE sequence = 2")
    scenario.store = scenario.open()
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE
    assert scenario.counts() == (2, 2)


def test_reordered_record_is_detected(scenario):
    """40. Swapping two records breaks the recorded ordering."""
    scenario.reach(S.EXECUTION_STARTED)
    scenario.store.close()
    with scenario.raw() as connection:
        connection.execute("UPDATE recovery_event SET sequence = 99 WHERE sequence = 1")
        connection.execute("UPDATE recovery_event SET sequence = 1 WHERE sequence = 2")
        connection.execute("UPDATE recovery_event SET sequence = 2 WHERE sequence = 99")
    scenario.store = scenario.open()
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_duplicated_or_spliced_record_is_detected(scenario):
    """41. An exact duplicate is refused; a spliced copy breaks chain continuity."""
    scenario.reach(S.EXECUTION_STARTED)
    scenario.store.close()
    insert = ("INSERT INTO recovery_checkpoint (checkpoint_id, project_id, task_id, execution_id,"
              " sequence, payload, fingerprint, previous_fingerprint, request_digest,"
              " idempotency_key) VALUES ('spliced', ?, ?, ?, 3, ?, ?, ?, ?, 'spliced-key')")
    with scenario.raw() as connection:
        row = connection.execute(
            "SELECT payload, fingerprint, previous_fingerprint, request_digest"
            " FROM recovery_checkpoint WHERE sequence = 1").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(insert, (PROJECT, TASK, EXECUTION, row[0], row[1], row[2], row[3]))
        connection.execute(insert, (PROJECT, TASK, EXECUTION, row[0], "0" * 64, row[2], row[3]))
    scenario.store = scenario.open()
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_corruption_never_auto_repairs(scenario):
    """42. A corrupt chain stays corrupt; nothing is rewritten or skipped."""
    scenario.reach(S.EXECUTION_STARTED)
    tamper(scenario, "recovery_checkpoint", "previous_fingerprint", "f" * 64, sequence=2)
    query = ("SELECT sequence, payload, fingerprint, previous_fingerprint FROM recovery_checkpoint"
             " ORDER BY sequence")
    with scenario.raw() as connection:
        before = connection.execute(query).fetchall()
    for _attempt in range(3):
        assessment = scenario.assess()
        assert assessment.action is A.BLOCK_CORRUPT_STATE
        assert assessment.last_valid_checkpoint is None and assessment.state is None
    with pytest.raises(RecoveryError) as error:
        scenario.store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
    assert error.value.code == "CHAIN_CORRUPT"
    with scenario.raw() as connection:
        assert connection.execute(query).fetchall() == before


def test_unknown_state_blocks(scenario):
    """43. A state outside the enumeration is never decoded or guessed."""
    scenario.reach(S.PLANNED)
    payload = scenario.payload("recovery_checkpoint", 1)
    payload["state"] = "TOTALLY_UNKNOWN"
    tamper(scenario, "recovery_checkpoint", "payload", canonical(payload))
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE


def test_unknown_field_blocks(scenario):
    """44. An unexpected payload field fails closed before any digest check."""
    scenario.reach(S.PLANNED)
    payload = scenario.payload("recovery_checkpoint", 1)
    payload["injected_field"] = "anything"
    tamper(scenario, "recovery_checkpoint", "payload", canonical(payload))
    assert scenario.assess().action is A.BLOCK_CORRUPT_STATE
    with pytest.raises(RecoveryError) as error:
        recovery._decode(RecoveryCheckpoint, canonical(payload), "0" * 64)
    assert error.value.code == "CHAIN_CORRUPT"


# 45-52. Bounds, sanitisation and non-disclosure ---------------------------

def test_oversized_record_blocks_before_the_write(tmp_path):
    """45. The size bound is enforced before anything reaches the database."""
    scenario = Scenario(tmp_path, max_record_bytes=256)
    try:
        with pytest.raises(RecoveryError) as error:
            scenario.step(S.PLANNED)
        assert error.value.code == "RECORD_LIMIT"
        assert scenario.counts() == (0, 0)
    finally:
        scenario.store.close()


@pytest.mark.parametrize("value", ["a\x00b", "\ud800", "a b", "-leading", "x" * 200, "",
                                   "a'; DROP TABLE recovery_checkpoint; --"])
def test_malformed_identifier_blocks(scenario, value):
    """46. NUL, surrogate, oversized and SQL-shaped identifiers are refused."""
    for field in ("task_id", "idempotency_key", "execution_id"):
        arguments = dict(task_id=TASK, execution_id=EXECUTION, idempotency_key="k")
        arguments[field] = value
        with pytest.raises(RecoveryError):
            scenario.store.append(to_state=S.PLANNED, expected_checkpoint_fingerprint=None,
                                  packet=scenario.packet, policy=scenario.policy,
                                  decision=scenario.decision, **arguments)
    assert scenario.counts() == (0, 0)
    assert table_names(scenario.database) == sorted(recovery.TABLES)


def test_bound_parameters_are_never_executed_as_sql(scenario):
    """47. A hostile value travels as a bound parameter and changes nothing."""
    scenario.reach(S.EXECUTION_STARTED)
    hostile = "x'; DROP TABLE recovery_checkpoint; --"
    rows = scenario.store._connection.execute(
        recovery.SELECT_IDEMPOTENT, (PROJECT, EXECUTION, hostile)).fetchall()
    assert rows == []
    assert table_names(scenario.database) == sorted(recovery.TABLES)
    assert scenario.assess().chain_valid is True


def test_no_untrusted_content_is_persisted(scenario, monkeypatch):
    """48/49/50/51/52. Only identifiers, digests and bounded codes are stored."""
    monkeypatch.setenv("ZERO_G4_TEST_MARKER", SECRET_ENVIRONMENT)
    scenario.reach(S.VERIFIED)
    raw_bytes = scenario.database.read_bytes()
    for secret in (SECRET_SUMMARY, SECRET_FILE_TEXT, SECRET_ENVIRONMENT, SECRET_STDOUT):
        assert secret.encode("utf-8") not in raw_bytes
    for banned in (b"stdout", b"stderr", b"summary", b"argv", b"prompt", b"password", b"token",
                   b"secret", b"environ"):
        assert banned not in raw_bytes.lower()
    names = {item.name for item in fields(RecoveryCheckpoint)}
    digests = {"packet_fingerprint", "policy_fingerprint", "decision_fingerprint",
               "attempt_fingerprint", "evidence_fingerprint", "previous_checkpoint_fingerprint"}
    with scenario.raw() as connection:
        payloads = [json.loads(row[0]) for row in
                    connection.execute("SELECT payload FROM recovery_checkpoint")]
    assert len(payloads) == 5
    for payload in payloads:
        assert set(payload) == names
        assert set(payload["reason_codes"]) <= set(recovery.REASON_CODES)
        assert payload["state"] in {state.value for state in RecoveryState}
        assert payload["repository_root"] == scenario.config.repository_root
        for name in digests:
            assert payload[name] is None or (len(payload[name]) == 64
                                             and set(payload[name]) <= set("0123456789abcdef"))


# 53-56. Fingerprints and decisions ----------------------------------------

def test_fingerprint_is_deterministic(scenario):
    """53. The same record always produces the same digest."""
    checkpoint = scenario.step(S.PLANNED)
    assert checkpoint.fingerprint() == checkpoint.fingerprint()
    reloaded = scenario.store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
    assert reloaded.fingerprint() == checkpoint.fingerprint()
    assert reloaded.canonical_json() == checkpoint.canonical_json()


@pytest.mark.parametrize("change", [
    {"state": S.ABANDONED}, {"sequence": 7}, {"evidence_fingerprint": "e" * 64},
    {"attempt_fingerprint": "e" * 64}, {"reason_codes": ("OPERATOR_DECISION",)},
    {"repository_root": "/other/root"}, {"task_id": "othertask"},
    {"packet_fingerprint": "e" * 64}, {"policy_fingerprint": "e" * 64},
    {"decision_fingerprint": "e" * 64},
])
def test_verdict_relevant_mutation_changes_the_fingerprint(scenario, change):
    """54. Every verdict-relevant field participates in the digest."""
    scenario.advance(*TERMINAL_PATH)
    checkpoint = scenario.step(S.VERIFIED)
    assert replace(checkpoint, **change).fingerprint() != checkpoint.fingerprint()


def test_fingerprints_are_explicitly_not_authentication(scenario):
    """55. A writer that rewrites the whole chain recomputes every digest."""
    checkpoint = scenario.step(S.PLANNED)
    assert checkpoint.fingerprint_kind == "SHA256_INTEGRITY_ONLY_NOT_AUTHENTICATED"
    scenario.store.close()
    with scenario.raw() as connection:
        payload, stored = connection.execute(
            "SELECT payload, fingerprint FROM recovery_event WHERE sequence = 1").fetchone()
        event = recovery._decode(RecoveryEvent, payload, stored)
        forged = replace(checkpoint, reason_codes=("OPERATOR_DECISION",))
        forged_event = replace(event, reason_codes=("OPERATOR_DECISION",),
                               checkpoint_fingerprint=forged.fingerprint())
        connection.execute(
            "UPDATE recovery_checkpoint SET payload = ?, fingerprint = ? WHERE sequence = 1",
            (forged.canonical_json(), forged.fingerprint()))
        connection.execute(
            "UPDATE recovery_event SET payload = ?, fingerprint = ? WHERE sequence = 1",
            (forged_event.canonical_json(), forged_event.fingerprint()))
    scenario.store = scenario.open()
    accepted = scenario.store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
    assert accepted.reason_codes == ("OPERATOR_DECISION",)
    assert scenario.assess().chain_valid is True


def test_recovery_action_mapping_is_deterministic():
    """56. The decision table is total over every state and has no free choice."""
    assert set(RECOVERY_DECISIONS) == set(RecoveryState) | {None}
    assert set(LEGAL_TRANSITIONS) == set(RecoveryState) | {None}
    for state, (reconstructed, action, reverify, reason) in RECOVERY_DECISIONS.items():
        assert type(action) is RecoveryAction
        assert type(reverify) is bool
        assert reason in recovery.REASON_CODES
        assert reconstructed is None or type(reconstructed) is RecoveryState
        if state in (S.EXECUTION_STARTED, S.EXECUTION_REPORTED, S.VERIFICATION_STARTED):
            assert reverify is True and action is A.REVERIFY_WORKSPACE
    assert RECOVERY_DECISIONS[S.VERIFIED][1] is A.NO_ACTION
    assert LEGAL_TRANSITIONS[S.ABANDONED] == frozenset()
    assert LEGAL_TRANSITIONS[None] == frozenset({S.PLANNED})
    assert S.EXECUTION_STARTED not in LEGAL_TRANSITIONS[S.VERIFIED]


def test_empty_chain_resumes_planning(scenario):
    """Decision table. No durable record means planning may safely resume."""
    assessment = scenario.assess()
    assert (assessment.state, assessment.action) == (None, A.RESUME_PLANNING)
    assert assessment.chain_valid is True
    assert assessment.reverification_required is False
    assert assessment.reason_codes == ("NO_DURABLE_RECORD",)


def test_earlier_verified_checkpoint_offers_a_retry_point(scenario):
    """Decision table. A later failure after a verified checkpoint is retryable."""
    scenario.reach(S.VERIFIED)
    scenario.step(S.REQUIRES_REVERIFICATION, attempt=scenario.attempt)
    scenario.step(S.VERIFICATION_STARTED)
    scenario.step(S.FAILED)
    assessment = scenario.assess()
    assert assessment.action is A.RETRY_FROM_VERIFIED_CHECKPOINT
    assert "EARLIER_VERIFIED_CHECKPOINT" in assessment.reason_codes
    assert assessment.reverification_required is True


# 57-64. Reality boundary --------------------------------------------------

def test_recovery_never_invokes_execution_or_verification(scenario, monkeypatch):
    """57/58/59. A full lifecycle runs without any runner, adapter or verifier."""
    import zero_core.engineering_execution as execution
    import zero_core.engineering_verification as verification
    import zero_core.process_runner as process_runner

    def forbidden(*args, **kwargs):
        raise AssertionError("recovery must not invoke execution or verification")

    monkeypatch.setattr(process_runner.LocalProcessRunner, "run", forbidden)
    monkeypatch.setattr(execution, "execute_attempt", forbidden)
    monkeypatch.setattr(verification.IndependentVerifier, "verify", forbidden)
    monkeypatch.setattr(verification.IndependentVerifier, "capture_pre", forbidden)
    monkeypatch.setattr(verification.LocalWorkspaceObserver, "observe", forbidden)
    scenario.reach(S.VERIFIED)
    scenario.restart()
    assert scenario.assess().state is S.VERIFIED


def test_recovery_writes_nothing_outside_the_trusted_directory(scenario):
    """60. A transition and an assessment touch no project or runtime path."""
    script = r'''
import os, sys, json, importlib.util
sys.path.insert(0, sys.argv[1])
directory, fixture, execution_id, root, database = sys.argv[2:7]
spec = importlib.util.spec_from_file_location("writer", fixture)
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)
from zero_core.engineering_recovery import RecoveryState, open_recovery_store
configuration, packet, policy, decision = writer.build(root, directory, database)
store = open_recovery_store(configuration, clock=writer.FixedClock(),
                            id_source=writer.SequentialIdentifiers("audit"))
touched = []


def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            touched.append(str(args[0]))
    if event in ("os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.system", "subprocess.Popen"):
        touched.append(event)
    if event.startswith("socket."):
        touched.append(event)


sys.addaudithook(audit)
store.append(task_id="task", execution_id=execution_id, to_state=RecoveryState.PLANNED,
             expected_checkpoint_fingerprint=None, idempotency_key="auditkey",
             packet=packet, policy=policy, decision=decision)
store.assess(task_id="task", execution_id=execution_id)
store.close()
print(json.dumps(touched))
'''
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script, str(REPOSITORY_ROOT), str(scenario.directory),
         str(FIXTURE), "auditattempt", str(scenario.root), str(scenario.database)],
        capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    touched = json.loads(completed.stdout.strip().splitlines()[-1])
    trusted = Path(scenario.config.recovery_directory).resolve()
    for entry in touched:
        assert not entry.startswith(("os.", "subprocess.", "socket.")), entry
        resolved = Path(entry).resolve()
        assert resolved == trusted or trusted in resolved.parents, entry


def test_existing_gate_modules_are_not_mutated():
    """61-64. G4 consumes G1-G3 read-only; those suites are run separately."""
    import zero_core.engineering_contracts as contracts
    import zero_core.engineering_execution as execution
    import zero_core.engineering_verification as verification
    for module in (contracts, execution, verification):
        assert not hasattr(module, "RecoveryStore")
        assert not hasattr(module, "TrustedRecoveryConfiguration")
        assert Path(module.__file__).resolve() != MODULE_PATH
    assert issubclass(RecoveryError, ValueError)
    assert recovery.SCHEMA_VERSION == 1


def test_configuration_rejects_unsupported_durability_and_deletion(tmp_path):
    """Trust boundary. Only the documented durability mode and a retention policy
    without automatic destructive deletion are accepted."""
    root = tmp_path / "repo"
    root.mkdir()
    directory = tmp_path / "recovery"
    directory.mkdir()
    common = dict(project_id=PROJECT, repository_root=root.resolve().as_posix(),
                  recovery_directory=directory.resolve().as_posix(),
                  database_path=(directory / "r.sqlite3").as_posix())
    for invalid in (dict(durability="WAL"), dict(schema_version=2), dict(busy_timeout_ms=0),
                    dict(busy_timeout_ms=10 ** 9), dict(max_record_bytes=8), dict(project_id="")):
        with pytest.raises(RecoveryError):
            TrustedRecoveryConfiguration(**{**common, **invalid})
    with pytest.raises(RecoveryError):
        RetentionPolicy(automatic_deletion_enabled=True)
    configuration = TrustedRecoveryConfiguration(**common)
    assert configuration.durability is DurabilityMode.FULL_SYNCHRONOUS_DELETE_JOURNAL
    assert configuration.retention.automatic_deletion_enabled is False
    assert configuration.fingerprint() == TrustedRecoveryConfiguration(**common).fingerprint()


def test_durability_pragmas_are_enforced_on_every_connection(scenario):
    """Durability. Foreign keys, FULL synchronous, rollback journal, bounded wait."""
    connection = scenario.store._connection
    assert int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
    assert int(connection.execute("PRAGMA synchronous").fetchone()[0]) == 2
    assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "delete"
    assert int(connection.execute("PRAGMA busy_timeout").fetchone()[0]) == \
        scenario.config.busy_timeout_ms


def test_closed_store_refuses_every_operation(scenario):
    """Durability. Handles close deterministically and stay closed."""
    scenario.step(S.PLANNED)
    scenario.store.close()
    scenario.store.close()
    for call in (lambda: scenario.store.assess(task_id=TASK, execution_id=EXECUTION),
                 lambda: scenario.store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)):
        with pytest.raises(RecoveryError) as error:
            call()
        assert error.value.code == "STORE_CLOSED"
    scenario.store = scenario.open()


# Crash scenarios ----------------------------------------------------------

def run_writer(mode, marker, root, directory, database, execution_id=EXECUTION, key="crashkey"):
    """Start a real writer, wait for its marker, then terminate it abruptly."""
    process = subprocess.Popen(
        [sys.executable, "-B", str(FIXTURE), mode, str(root), str(directory), str(database),
         execution_id, key],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    seen = []

    def reader():
        for line in process.stdout:
            seen.append(line.strip())
            if line.strip() == marker:
                return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(120)
    try:
        assert marker in seen, process.stderr.read()
    finally:
        process.kill()
        process.wait(60)
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize("mode,marker,checkpoints", [
    ("pre", "READY_PRE", 0), ("mid", "IN_TRANSACTION", 0), ("post", "COMMITTED", 1),
])
def test_process_kill_leaves_complete_state_only(tmp_path, mode, marker, checkpoints):
    """Crash. Killing before, during or after commit never leaves half a pair.

    This proves process-termination atomicity only. It does not demonstrate
    power-loss, host-failure or filesystem-rollback durability.
    """
    scenario = Scenario(tmp_path)
    scenario.store.close()
    run_writer(mode, marker, scenario.root, scenario.directory, scenario.database)
    store = scenario.open()
    try:
        assert scenario.counts() == (checkpoints, checkpoints)
        assessment = store.assess(task_id=TASK, execution_id=EXECUTION)
        assert assessment.chain_valid is True
        assert assessment.state is (S.PLANNED if checkpoints else None)
        assert assessment.action is A.RESUME_PLANNING
        assert table_names(scenario.database) == sorted(recovery.TABLES)
    finally:
        store.close()


def test_lost_response_is_resolved_by_idempotency_not_by_appending(tmp_path):
    """Crash. A commit whose response was lost resolves to the stored record."""
    scenario = Scenario(tmp_path)
    scenario.store.close()
    run_writer("post", "COMMITTED", scenario.root, scenario.directory, scenario.database)
    assert scenario.counts() == (1, 1)
    fixture = load_fixture()
    store = scenario.open(clock=fixture.FixedClock(),
                          ids=fixture.SequentialIdentifiers("crashkey"))
    try:
        stored = store.latest_checkpoint(task_id=TASK, execution_id=EXECUTION)
        replayed = store.append(
            task_id=TASK, execution_id=EXECUTION, to_state=S.PLANNED,
            expected_checkpoint_fingerprint=None, idempotency_key="crashkey",
            packet=scenario.packet, policy=scenario.policy, decision=scenario.decision)
        assert replayed.fingerprint() == stored.fingerprint()
        assert replayed.checkpoint_id == stored.checkpoint_id
        assert scenario.counts() == (1, 1)
        with pytest.raises(RecoveryError) as error:
            store.append(task_id=TASK, execution_id=EXECUTION, to_state=S.PLANNED,
                         expected_checkpoint_fingerprint=None, idempotency_key="crashkey",
                         packet=scenario.packet, policy=scenario.policy, decision=scenario.decision,
                         reason_codes=("OPERATOR_DECISION",))
        assert error.value.code == "IDEMPOTENCY_CONFLICT"
        assert scenario.counts() == (1, 1)
    finally:
        store.close()
