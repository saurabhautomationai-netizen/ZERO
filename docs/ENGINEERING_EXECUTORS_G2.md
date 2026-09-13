# G2A: safe executor boundary and stateless adapter planning

G2A supplies an injected process port and fail-closed planning. It contains no
subprocess runner and makes no real executor execution claim. Codex and Goose
are replaceable adapters; ZERO remains the source of truth for permission,
project state, verification, checkpoints and milestone completion.

## Gate and trusted configuration

`execute_attempt` explicitly calls G1 `validate_binding(packet, policy)` and
`permits_unattended_execution(packet, policy)`. Only the exact matching LOW_RISK
decision can reach a runner. DENIED, HITL_REQUIRED, stale fingerprints, tampered
classification and trusted workspace mismatches return BLOCKED without runner
calls and with zero effect/test claims. A rejected stale decision cannot itself
pass G1 result binding; the BLOCKED record is diagnostic, not a repaired grant.
Staleness here means changed packet/policy binding, not approval expiry.

Immutable `TrustedAdapterConfiguration` is supplied by the trusted application,
outside packet control. It pins project, canonical existing local repository and
exact native executable. Packet and policy must both match that configuration.
Path checks reject missing paths, symlinks and Windows reparse points (including
junctions), UNC paths, relative paths and unsupported host assumptions. Checks
repeat before planning. POSIX requires executable permission; Windows requires
a native `.exe`, never a PowerShell/batch launcher. These checks do not establish
binary identity, race-free containment, mount isolation or trusted provisioning.
Invalid configuration fails construction before any runner can be invoked.

No approval boolean or token exists. SHA-256 is an integrity fingerprint, not a
signature. Approval authentication, expiry, revocation and replay persistence
are intentionally absent. Authenticated HITL execution is deferred to the
authoritative approval integration, including its own binding and replay checks.
This scoped roadmap supersedes the broader future-G2 expectations in the G1 doc.

## Process port and security

`ProcessInvocation` is immutable: exact argv tuple, stdin text, canonical cwd,
copied immutable explicit environment and requested timeout/output byte limits.
There is no shell-string field. A future runner MUST use `shell=False`, pass the
environment exactly, and never merge the parent environment. The closed non-secret
allowlist currently admits only canonical home/temp/system directories and a
small locale vocabulary; no PATH, API keys, provider tokens or packet environment.
Trusted provisioning must ensure directory names and file targets contain no
credentials; string validation cannot identify every possible secret. No free-form
context is accepted, and command arguments never enter the Codex prompt.

`ProcessOutcome` records exit/timeout/cancellation/missing-executable state,
runner-supplied bounded streams, truncation indicators and UTC monotonic times.
Nonzero exit maps to FAILED, timeout to TIMEOUT, cancellation to CANCELLED and
missing executable to BLOCKED. Runner exceptions are reduced to fixed short
summaries. External errors/prose never appear in results. Output marked truncated,
over the requested byte limit, malformed or unknown fails closed. Post-return
checks do not enforce streaming memory/output caps or terminate processes.

The injected runner and adapter are trusted application dependencies, not packet
plugins. G2A does not stop an arbitrary supplied runner from violating its port.
No credential material belongs in packets, stdin, argv, logs or results.
Credential-broker integration and isolated authentication provisioning are deferred.

## Locally established CLI support (2026-09-13)

Read-only `codex --version` returned `codex-cli 0.154.0`. Local `codex exec --help`
documents `exec`, stdin `-`, `--json` JSONL, `-C`, `--ephemeral`, `--color never`,
`--sandbox read-only`, `--ignore-user-config`, `--strict-config` and `-c` overrides.
`CodexAdapter.preview` deterministically constructs these flags, pins
`model_provider="openai"`, uses the trusted CODEX_HOME and emits only structured
read-file instructions on stdin. It does not use ambient FreeLLM/custom-provider
configuration. It supports only READ_FILE planning; command profiles and writing
operations require later semantic enforcement.

Local help does **not** establish the versioned exec-event grammar or complete
project config/MCP/extension/hook isolation. Accordingly Codex `plan` returns
unsupported via BLOCKED, and its version-aware parser supports no event schema
yet. Even plausible `turn.completed` JSON is rejected. The preview is not a
safe-to-launch grant. Do not wire it directly to a process runner. Enable actual
Codex invocation only after those capabilities are established and tested.

Local `goose --version` and `goose run --help` failed during log initialization
with permission denied. Exact stdin, no-session, no-profile, structured output
and extension-isolation behavior could not be established. Goose therefore
returns unsupported via BLOCKED; no guessed argv is emitted. The intended future
shape is stateless `goose run` with stdin, no session/profile and no MCP or ambient
extensions. Session IDs will never be authoritative recovery state.

Tests use a clearly synthetic `fixture_v1` output grammar to exercise reported
SUCCESS through the neutral boundary. It is not represented as a CLI schema.
Neither adapter classifies risk, authenticates approvals, verifies artifacts,
updates checkpoints or changes milestones. No external prose is converted into
file/test evidence; all such result fields stay empty/zero. SUCCESS is only an
unverified reported attempt, even when produced by a conforming future adapter.

## Remaining phases

| Phase | Responsibility |
| --- | --- |
| G2A | Pure boundary, immutable process records, stateless planning, fake runners |
| G2B | Real subprocess enforcement: shell=False, isolated environment/config, process-tree cancellation, timeout and output caps, OS containment and race protection |
| G3 | Independent verification and observed file/test evidence |
| G4 | Durable recovery and authoritative checkpoint persistence |
| G5 | Independent review |
| G6 | Unattended queue under established gates |
| Later authenticated HITL | Authoritative human approval integration; no G2A override |

## Isolated validation

Run separately to bypass the held parent conftest and disable bytecode/cache:

```text
python -B -m pytest --confcutdir=tests/g1_contracts -p no:cacheprovider tests/g1_contracts -q
python -B -m pytest --confcutdir=tests/g2_executors -p no:cacheprovider tests/g2_executors -q
```

PASS applies only to G2A pure boundary/fake-runner scope. It does not certify real
executor execution, OS containment, HITL authorization, verification or autonomous
operation. No existing runtime integration or data migration is introduced.
