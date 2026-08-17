# ADR-004: Keyword/Token Routing Before Embedding-Based Routing

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
When a user submits a natural-language task, [`AgentRegistry.resolve()`](file:///f:/AI%20Automation/Projects/Zero/zero_core/agent_registry.py) must rank and select the best candidate specialist among 5 native agents and 269 Agency-agents personas.

## Problem
Should ZERO implement semantic embeddings and vector search immediately in Phase 1 / Milestone M4, or utilize a deterministic keyword/token-matching mechanism first?

## Decision
Task routing in core milestones M1–M4 uses a **two-tier deterministic keyword and token-overlap routing engine**:
1. **Tier 1 (Native Priority)**: Substring matching against curated keyword tuples for native domain agents (giving ZERO's native agents first refusal).
2. **Tier 2 (Agency Token Overlap)**: Exact word token overlap matching (alphanumeric tokens $\ge 3$ characters, with stopword removal) across agent names, descriptions, divisions, and usage summaries.

Embedding-based vector search is deferred to Milestone M8 (Memory & RAG).

## Why We Made the Decision
1. **Zero External Machine Learning Dependencies**: Keeps the core lightweight, fast, and 100% testable without downloading gigabytes of model weights or requiring external API keys.
2. **Deterministic & Debuggable**: Scoring can be traced directly to specific matching tokens, simplifying automated test verification and eliminating black-box routing anomalies.
3. **Prevention of Substring False Positives**: Tokenization fixes edge cases where generic words like "design" unintentionally matched words like "designing" in unrelated specialist descriptions.
4. **Stable Interface Contract**: The output format (`RegistryMatch` with `best` and `alternatives`) remains identical when vector embeddings are introduced in M8.

## Alternatives Considered
- **Vector Embeddings (sentence-transformers / OpenAI embeddings)**: Deferred to M8 until vector infrastructure (pgvector / Supabase) is formalized.
- **LLM-Based Router**: Rejected due to latency ($> 1\text{ s}$ per query), API cost, and circular dependency of needing an LLM call to find an LLM persona.

## Consequences
- **Positive**: Blazing fast routing ($< 5\text{ ms}$), completely offline, zero inference costs, reproducible tests.
- **Negative**: Lacks semantic understanding of synonyms (e.g., "expenditure" vs "spending") until M8 semantic retrieval is activated.
