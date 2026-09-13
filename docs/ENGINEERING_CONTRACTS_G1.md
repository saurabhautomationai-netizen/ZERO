# G1: Executor-neutral engineering contracts

G1 defines a pure boundary for future controlled engineering execution. It does
not execute a worker, approve an operation, read a workspace, or advance project
state. The leaf module `zero_core.engineering_contracts` imports neither the
engineering package nor stores, adapters, workers or configuration.

## Records and invariants

All records use Pydantic v2 strict validation, reject extra fields, and accept
only integer `schema_version: 1`. IDs contain ASCII letters, digits, underscores
or hyphens, start with an alphanumeric character and have at most 128 characters.
Models are frozen and collections are tuples. `model_copy(update=...)` validates
the resulting record. Use constructors, `model_validate`, or
`model_validate_json` at boundaries; never Pydantic's unvalidated
`model_construct` or arbitrary object mutation.

| Contract | Meaning |
|---|---|
| `RequestedOperation` | A closed action plus exact file target, or a configured command ID, exact argv tuple and working directory. |
| `TaskPacket` | Stable packet/project/task/milestone identity, trusted root, policy ID/version, context digest, nonempty unique operations and UTC creation time. |
| `WorkspacePolicy` | Trusted project/root binding and explicit operation rules. Empty rules deny everything. |
| `PermissionDecision` | Decision ID, exact packet/policy digests, outcome, reason codes and UTC evaluation time. |
| `EngineeringExecutionResult` | One identified execution attempt and its reported net changes/counts. It is not verified completion. |
| `EvidenceRecord` | Project/task/execution/check identity, exact execution digest, producer provenance, PASS/FAIL/BLOCKED and optional hashed evidence artifact. |

The small `OperationRule` value object associates one complete requested
operation with a permission outcome. It is not another executor abstraction.

File targets have one portable spelling: forward-slash-separated relative
components. Empty targets, absolute/drive-relative paths, backslashes, UNC and
device paths, traversal, repeated separators, alternate data streams, percent
encoding, wildcards, control characters and Windows reserved names are rejected.
Command working directory `.` explicitly means the packet root; file targets
cannot be `.`. Roots must be lexically absolute POSIX paths or normalized Windows
paths with uppercase drives and forward slashes. No path is resolved or opened.
The application must supply a trusted root; a valid string is not proof of trust.

RUN_COMMAND cannot carry a file target or arbitrary shell command. It uses a
safe persistence-key `command_id`, exact structured argv tokens and relative cwd.
Obvious shell syntax is rejected in arguments. File operations cannot smuggle
command fields. G2 must map IDs to trusted executable profiles and enforce argument
semantics: lexical argv validation cannot prove that a configured program is safe.

Execution timestamps are UTC-aware and monotonic. Counts are strict nonnegative
integers; executed equals passed + failed + skipped (including skipped cases is
the explicit G1 accounting convention). SUCCESS cannot claim failed tests.
Created/modified/deleted lists describe net changes, are individually unique and
mutually disjoint, including case-insensitive aliases. G2 must reduce multi-step
changes to net outcomes before producing a result.

## Fail-closed permission behavior

`WorkspacePolicy.classification` performs exact operation fingerprint lookup,
not prefix, substring, wildcard or capability-name matching. A changed command
ID, argument, cwd, target or action requires its own rule. Unknown actions fail
schema validation; valid but unlisted operations evaluate to DENIED. Root,
project, policy ID or version mismatch also evaluates to DENIED.

Aggregation is DENIED > HITL_REQUIRED > LOW_RISK. `evaluate` returns a decision
bound to the whole packet and whole policy, including their versions.
`validate_binding` checks both fingerprints and recomputes outcome/reason codes,
rejecting fabricated or stale decisions. `permits_unattended_execution` returns
true only for a matching LOW_RISK decision. This classification is not an OS
permission grant or a sandbox.

There is no approval boolean, mutation method or approval override in G1.
HITL_REQUIRED remains non-executable by this unattended predicate. G2 must obtain
an authenticated external approval bound to the same packet, policy and decision,
check expiry/revocation/replay, and recheck the actual operation immediately before
execution. DENIED must never enter that approval path. A denied decision can be
linked only to a BLOCKED result reporting no effects or tests.

## Execution, verification, review and completion

Worker-reported SUCCESS describes an attempt. It does not imply that artifacts
exist, that tests actually ran, that a review passed, that a checkpoint exists or
that a task/milestone is complete. Result records expose none of those completion
fields. Identity and fingerprint binding are explicit `validate_binding` checks
which the G2 ingestion boundary must always invoke.

Evidence binds to an exact result, not just a reusable task ID. PASS requires a
VERIFIER producer and an artifact reference with SHA-256. A WORKER assertion
cannot be PASS. Binding rejects project/task/execution/digest mismatches,
post-execution observations dated before completion, and an executor claiming to
be its own independent verifier. FAIL/BLOCKED can record incomplete observations.
A PASS concerns one identified check, not the entire task; other checks may fail.

These constraints validate claims and relationships. A caller can still lie about
producer identity or provide a nonexistent artifact. G2 authenticates provenance,
checks the artifact and digest against actual observations, and determines the
required check set. Independent review and existing HITL gates remain separate
application decisions. Checkpoint persistence and milestone completion are later
steps and must not be inferred from any single record.

## Serialization and fingerprints

Use `model_dump_json` / `model_validate_json` for wire round trips. Strict Python
construction expects typed tuples/datetimes; JSON arrays and ISO UTC timestamps
are accepted through JSON validation. All fields are JSON-safe typed values;
there are no arbitrary metadata, environment, credential or provider fields.

`canonical_json` revalidates the record and emits all fields, including defaults,
schema version, UTC timestamps and nulls, with sorted keys, compact separators,
ASCII escapes and no NaN/Infinity. `fingerprint` hashes those UTF-8 bytes with
SHA-256. Every packet/policy field is covered, including operation arguments and
context fingerprint. Array order is significant; reordering produces a new
fingerprint. This is the G1 canonical format, not a claim of RFC 8785 compliance.
Changing serialization requires an explicit schema/version strategy.

Fingerprints are integrity bindings, not signatures or proof of approval. Context
digests must be computed over the actual sanitized context outside this module.
No artifact contents, worker output logs or secrets belong in these records.
Summary fields should contain sanitized text; schema validation cannot detect all
secrets in otherwise valid text.

## Layer ownership and compatibility

- Domain: this leaf module, strict records, lexical checks, pure classification,
  canonical JSON and binding validators.
- Application: trusted packet/policy construction, identity resolution, approval
  orchestration, invocation sequence, required checks, independent review and
  completion decisions.
- Adapters: filesystem containment, command profiles, worker execution, verifier
  observations, provenance authentication and persistence.
- Interfaces: display decisions/evidence and collect authenticated human actions.

No existing file or model is modified. `TaskItem` remains the planning model;
G2 maps its identity into a packet. `WorkerResult` remains the existing worker
payload; G2 maps its reported counts and net file changes into the narrower
attempt result, accounting explicitly for skipped tests. The conversational
`executors.ExecutionResult` is unchanged. `Checkpoint` remains the persistence
model; an application-level evidence-to-checkpoint link is deferred. No legacy
data migration, package initialization change or automatic deserializer fallback
is introduced.

## G2 and the future engineering-agent roadmap

The intended future flow is Loop Agent -> validated packet -> trusted policy and
permission decision -> controlled executor -> result -> verifier -> evidence ->
checkpoint -> independent reviewer/HITL. G1 supplies contracts for this sequence;
it does not rewire the current runtime.

G2 must enforce symlink/junction and real-path containment, deny protected paths,
prevent TOCTOU escapes, constrain command effects and subprocesses, and enforce
network/environment/resource/time limits. It must authenticate policies,
approvals and verifier producers, prevent replay, enforce binding validators,
capture actual filesystem/test evidence, and preserve existing gate authority.

This supports a future Devin-equivalent engineering workflow through explicit,
auditable task boundaries and swappable executors. It grants no unrestricted
autonomy: planning, execution permission, verification and human authority remain
separate. G1 PASS means ready for G2 integration, not autonomous execution complete.

## Isolated validation

Run only from the canonical repository root:

```text
python -B -m pytest --confcutdir=tests/g1_contracts -p no:cacheprovider tests/g1_contracts -q
```

Tests use synthetic records, no operational stores or held tests. The import
test uses a fresh `-B` interpreter with an audit guard against writes/processes/
network activity and an import guard against runtime modules. Temporary test
directories are used only for the import-inertness check. No worker is invoked.
