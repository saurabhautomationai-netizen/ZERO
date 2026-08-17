# ADR-004: Keyword/Token-Based Routing (Defer Embeddings to Phase 2)

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

`AgentRegistry.resolve(task)` must rank candidate agents for a given task string. Phase 1 has no Memory/RAG, no embedding model, and no usage data to tune against.

## Decision

**Phase 1 routing uses naive keyword/token matching** — deliberately simple, intentionally not semantic.

### Native Agents
- Matched by **substring** against curated `keywords` tuple (e.g., "subscription" matches "subscriptions")
- Keywords are short, hand-picked, domain-specific
- Native agents get **first refusal** — ZERO owns these domains

### Agency-agents Specialists
- Matched by **exact token overlap** (not substring)
- Task tokens: `_tokenize(task)` → lowercase alphanumeric, stopwords removed, length ≥ 3
- Spec tokens: `_tokenize(name + description + when_to_use + division)`
- Score = `|task_tokens ∩ spec_tokens|`
- Ranked by score descending

**Why token not substring?**  
Substring matching caused a real bug: "design a threat model" matched "Anthropologist" because its `when_to_use` contains "Designing culturally coherent societies" → "design" ⊂ "designing". Token matching avoids this.

## Consequences

### Positive
- **Zero dependencies** — no embedding model, no vector DB, no ML
- **Deterministic, debuggable** — can explain exactly why an agent ranked
- **Testable** — synthetic fixtures verify behavior exactly
- **Contract stable** — `resolve(task) → RegistryMatch` unchanged when embeddings arrive

### Negative
- **Lower recall** — misses semantic matches (e.g., "spending" vs "expenses")
- **No synonym handling** — "budget" ≠ "spending plan"
- **Manual keyword curation** for native agents

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Sentence-transformers + cosine similarity | Premature without usage data; adds heavy deps |
| LLM-based routing (classify task → agent) | Circular — need an agent to route to an agent; latency/cost |
| BM25 / Tantivy | Overkill for 274 agents; still keyword-based |

## Migration Path (Phase 2)
When Memory/RAG exists:
1. Embed all agent specs (native + agency) into vector store
2. Replace `resolve()` internals with embedding similarity search
3. Keep `RegistryMatch` return type identical — zero caller changes
4. Fallback to keyword routing if embedding service unavailable

## References
- `zero_core/agent_registry.py:AgentRegistry.resolve()` (lines 258-299)
- `zero_core/agent_registry.py:_tokenize()`, `_STOPWORDS`
- `tests/test_agent_registry.py::test_resolve_does_not_match_substring_inside_a_different_word` — regression test
- `ARCHITECTURE.md` — "Key Architectural Decisions #4"