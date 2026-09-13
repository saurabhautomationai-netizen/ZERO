"""Crash fixture: a real G4 writer that can be killed at a chosen point.

Run as a subprocess against a throwaway temporary database only. The parent
waits for this process to print its marker, kills it, then reopens the store and
asserts what survived. Never point this at a ZERO runtime or data path.

Modes
-----
``pre``   open the store, then stop before any transaction begins.
``mid``   stop inside an uncommitted transaction, after the checkpoint row is
          inserted and before the event row is inserted.
``post``  stop after the commit succeeded but before the caller could use the
          returned checkpoint, so the response is lost but the record exists.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from zero_core.engineering_contracts import (  # noqa: E402
    OperationRule, RequestedOperation, TaskPacket, WorkspacePolicy,
)
from zero_core.engineering_recovery import (  # noqa: E402
    RecoveryState, TrustedRecoveryConfiguration, open_recovery_store,
)


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)
MARKERS = {"pre": "READY_PRE", "mid": "IN_TRANSACTION", "post": "COMMITTED"}
HOLD_SECONDS = 120


class FixedClock:
    def now(self):
        return NOW


class SequentialIdentifiers:
    def __init__(self, prefix):
        self.prefix = prefix
        self.count = 0

    def next_id(self):
        self.count += 1
        return "%s-%03d" % (self.prefix, self.count)


def build(repository_root, recovery_directory, database_path, project_id="project", task_id="task"):
    """Deterministic trusted configuration and G1 records for one attempt."""
    root = Path(repository_root).resolve().as_posix()
    configuration = TrustedRecoveryConfiguration(
        project_id=project_id, repository_root=root,
        recovery_directory=Path(recovery_directory).resolve().as_posix(),
        database_path=Path(database_path).as_posix(),
    )
    operation = RequestedOperation(action="CREATE_FILE", target="a.txt")
    packet = TaskPacket(
        packet_id="packet", project_id=project_id, task_id=task_id, milestone_id="milestone",
        repository_root=configuration.repository_root, policy_id="policy", policy_version=1,
        context_fingerprint="a" * 64, operations=(operation,), created_at=NOW,
    )
    policy = WorkspacePolicy(
        policy_id="policy", policy_version=1, project_id=project_id,
        repository_root=configuration.repository_root,
        rules=(OperationRule(operation=operation, outcome="LOW_RISK"),),
    )
    decision = policy.evaluate(packet, decision_id="decision", evaluated_at=NOW)
    return configuration, packet, policy, decision


def hold(marker):
    print(marker, flush=True)
    time.sleep(HOLD_SECONDS)


def main(argv):
    mode, repository_root, recovery_directory, database_path, execution_id, idempotency_key = argv
    if mode not in MARKERS:
        raise SystemExit("unknown mode")
    configuration, packet, policy, decision = build(repository_root, recovery_directory, database_path)
    store = open_recovery_store(configuration, clock=FixedClock(),
                                id_source=SequentialIdentifiers(idempotency_key))
    if mode == "pre":
        hold(MARKERS["pre"])
        return
    if mode == "mid":
        # The trace callback fires as the event INSERT is submitted, which is
        # after the checkpoint INSERT ran and before this transaction commits.
        def trace(statement):
            if str(statement).lstrip().upper().startswith("INSERT INTO RECOVERY_EVENT"):
                hold(MARKERS["mid"])

        store._connection.set_trace_callback(trace)
    store.append(
        task_id=packet.task_id, execution_id=execution_id, to_state=RecoveryState.PLANNED,
        expected_checkpoint_fingerprint=None, idempotency_key=idempotency_key,
        packet=packet, policy=policy, decision=decision,
    )
    hold(MARKERS["post"])


if __name__ == "__main__":
    main(sys.argv[1:])
