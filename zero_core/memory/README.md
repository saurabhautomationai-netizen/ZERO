# Memory / RAG — not implemented yet (Phase 2)

This directory is a placeholder so the architecture diagram in the top-level
README has a real location to point at. Nothing here is wired into the
Orchestrator or Agent Registry yet.

Planned scope, matching your stated stack (Supabase/pgvector, LangChain,
embeddings):

- A `store.py` wrapping a Supabase Postgres table with the `pgvector`
  extension — one table per memory domain to start (general conversation
  memory, Trading Coach memory, Finance context), not one giant table, so
  retrieval stays cheap and access control stays simple.
- An `embed.py` with a single `embed(text: str) -> list[float]` function so
  the rest of the codebase never imports an embedding provider directly —
  swapping providers later should mean editing one file.
- A `retrieve.py` with a `search(query: str, domain: str, k: int)` function
  that `Orchestrator.resolve()` will eventually call instead of (or in
  addition to) the current keyword-matching in
  `zero_core/agent_registry.py::AgentRegistry.resolve`.

Do not start this until the Phase 1 registry/orchestrator contract has been
exercised with real usage — retrieval quality is much easier to tune once
you know what kinds of tasks ZERO actually gets asked.
