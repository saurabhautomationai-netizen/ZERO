# ADR-005: LangGraph Optional (Pure-Python Fallback)

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

Orchestrator needs to execute a routing graph. LangGraph is the stated stack preference but adds a dependency.

Phase 1 graph is a single node: `route` → `END`. No conditional edges, no checkpointing, no multi-node flow.

## Decision

**LangGraph is optional**. `orchestrator.py` detects it at import time:

```python
try:
    from langgraph.graph import StateGraph, END
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False
```

- If available: compiles a `StateGraph` with one node (`route_node`)
- If not: `_run_fallback(task)` — 3-line pure Python equivalent

Tests run without LangGraph installed. The fallback path is the default in the test environment.

## Consequences

### Positive
- **Zero mandatory dependencies** for Phase 1 — only `pytest` required
- **Tests run anywhere** — no graph runtime needed
- **Defer install decision** — install LangGraph when multi-node graphs with conditional edges are needed (Phase 2+)
- **Same interface** — `Orchestrator.run()` and `execute()` work identically

### Negative
- **Two code paths** — minimal (7 lines graph vs 3 lines fallback)
- **No checkpointing/state** in fallback — acceptable for single-node Phase 1

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Require LangGraph | Adds dependency for zero benefit in Phase 1 |
| Implement own graph runtime | Reinventing LangGraph poorly; better to use it when needed |
| Use `langchain` instead | Same dependency issue; LangGraph is the graph layer |

## Migration Path
When Phase 2 needs multi-node graphs (e.g., `route → retrieve_memory → decide → execute`):
1. `pip install langgraph`
2. Expand `_build_graph()` with additional nodes/edges
3. Fallback path removed or kept for CI without deps
4. No interface changes to `Orchestrator`

## References
- `zero_core/orchestrator.py` — `Orchestrator._build_graph()`, `_run_fallback()`
- `requirements.txt` — LangGraph commented as optional
- `ARCHITECTURE.md` — "Key Architectural Decisions #5"