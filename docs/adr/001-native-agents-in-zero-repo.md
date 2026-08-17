# ADR-001: Native Agents Defined in ZERO Repository (Not Agency-agents Fork)

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

ZERO needs its own agent definitions for Finance, Trading, Trading Coach, Email, and Calendar agents. These agents:
- Require access to personal data (Postgres, MT5, Gmail, Calendar)
- Need integration with Memory/RAG, approval flows, and ZERO-specific workflows
- Are bound to personal context and credentials

The Agency-agents repository (`msitarzewski/agency-agents`) is a public library of 269 specialist personas, tracked as a git clone with `origin/main` upstream.

## Decision

**Native agent personas live in `zero_core/native_agents.py` inside the ZERO repository**, not as a "zero" division inside the Agency-agents clone.

Each native agent is an `AgentSpec` dataclass with:
- `name`, `slug` (prefixed `native/`), `division: "zero-native"`
- `description`, `keywords` (for Phase 1 routing)
- `integration_note` documenting how it wraps existing sibling projects

## Consequences

### Positive
- **No merge conflicts** with upstream Agency-agents `git pull`
- **No accidental push** of personal context/credentials to public fork
- **Full ownership** of agent schema evolution (can add fields like `approval_required`, `memory_namespace`)
- **Single source of truth** for ZERO's architecture — native agents are first-class, not bolted on

### Negative
- **Duplication of frontmatter pattern** — native agents mirror Agency-agents `AgentSpec` shape but don't share validation/linting
- **Two places to look** for agent definitions (mitigated: `AgentRegistry.get(slug)` unifies both)

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Scaffold `zero/` division in Agency-agents fork | Risks merge conflicts + accidental public push of personal agents |
| Symlink Agency-agents into ZERO | Doesn't solve personal-data-bound agents needing different schema |
| Embed native agents in Agency-agents upstream | Wrong ownership — these are personal, not general-purpose |

## References
- `zero_core/native_agents.py` — implementation
- `zero_core/agent_registry.py:AgentRegistry` — unified lookup
- `ARCHITECTURE.md` — "Key Architectural Decisions #1"