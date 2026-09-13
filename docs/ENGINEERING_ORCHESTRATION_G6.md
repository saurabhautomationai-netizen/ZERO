# G6A: Controlled unattended orchestration core

G6A is an inert, provider-neutral state-machine boundary. It uses only injected fake ports; it starts no daemon, provider, network service, subprocess, deployment, sandbox, or authenticated HITL workflow.

## Authority and states

The only graph is `QUEUED → LEASED → POLICY_CHECKED → EXECUTION_REPORTED → VERIFICATION_PENDING → VERIFIED → REVIEW_PENDING → REVIEWED → COMPLETED`. Defined failure exits are `BLOCKED`, `FAILED`, `CANCELLED`, and `REQUIRES_REVERIFICATION`; terminal states never transition. Recovery of an expired lease enters `REQUIRES_REVERIFICATION`, never assumes an external side effect was absent.

The coordinator first binds trusted project/root/configuration, then has G1 validate packet, policy, and decision. Only exact `LOW_RISK` reaches G2. G2 `SUCCESS` means only `EXECUTION_REPORTED`. G3 independent PASS plus G4 authoritative checkpoint verification are required before G5. G5 `APPROVED` is advisory evidence, not execution authority; completion requires the final G4 binding. G1 DENIED/HITL_REQUIRED call neither G2, G3, nor G5.

## Queue, budgets, cancellation, recovery

The injected repository owns deterministic sequence ordering and CAS claim/transition semantics. A live lease is exclusive, stale holders fail CAS, renewal/recovery are bounded by trusted configuration, and duplicate task IDs or conflicting idempotency content fail closed. Exact replay returns the stored result without calls.

All limits are immutable trusted configuration: queue/lease limits, wall time, steps, attempts, executions, verification, review, and deterministic bounded backoff. Counters are monotonic. Cancellation is sticky; pre-start cancellation performs no calls. A cancellation racing after execution creates uncertainty and `REQUIRES_REVERIFICATION`, never a rollback claim.

## Trust boundary and future work

Durable records are strict frozen dataclasses with bounded sanitized summaries and no prompts, credentials, secrets, raw provider output, shell strings, adapters, or external session IDs. Task input cannot select roots, policies, limits, or services. Unknown outcomes and malformed bindings fail closed.

G6A proves only fake-port coordinator behavior. G6B may integrate a runtime after separate security review. Authenticated HITL remains separate, and deployment remains independently HITL-gated. This module neither provides OS sandboxing nor production/provider integration.
