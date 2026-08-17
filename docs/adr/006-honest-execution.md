# ADR-006: Honest Execution — Answers OR Persona Handoff (No Fake LLM)

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

`Orchestrator.execute(task)` must produce a result after `run(task)` selects an agent. Three agent types exist:

1. **Native agents with real adapters** (Finance, Trading) — can produce real answers
2. **Native agents without adapters** (Trading Coach, Email, Calendar) — not implemented
3. **Agency-agents specialists** (269 personas) — require LLM invocation

## Decision

**`executors.py:execute()` returns `ExecutionResult` with honest semantics:**

| Agent Type | `needs_llm` | `answer` | `persona` |
|------------|-------------|----------|-----------|
| Native + adapter | `False` | Real answer (deterministic Python) | `None` |
| Native, no adapter | `False` | "X is not implemented yet" | `None` |
| Agency-agents | `True` | `None` | Full persona markdown |

**No LLM client exists in `zero_core`.** The interface layer (Web/Telegram/CLI) receives the persona and is responsible for calling an LLM.

## Consequences

### Positive
- **No fake answers** — never hallucinates on behalf of an agent
- **Clear contract** — caller knows exactly what to do: display answer, or call LLM with persona
- **Testable without LLM** — all 39 tests run with zero network/LLM calls
- **Security boundary** — core never sends prompts to external models

### Negative
- **Interface layer complexity** — must handle `needs_llm=True` branch
- **No "quick demo" mode** — can't show full conversation without wiring LLM

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Mock LLM responses in executors | Fake data → false confidence; hides integration issues |
| Call LLM directly from executors | Couples core to LLM provider; untestable; security boundary violation |
| Return "not implemented" for everything | Useless — Finance/Trading already work |

## Implementation Notes
- `NATIVE_EXECUTORS` dict maps every native slug to a callable — enforced by test
- `_not_implemented(name)` factory returns consistent stub message
- Agency path: `agency_adapter.load_persona(spec)` → returns raw markdown

## References
- `zero_core/executors.py` — `execute()`, `ExecutionResult`, `NATIVE_EXECUTORS`
- `zero_core/orchestrator.py:Orchestrator.execute()` — calls executors
- `tests/test_executors.py` — 6 tests covering all three cases
- `ARCHITECTURE.md` — "Delivered so far: Phase 1.6"