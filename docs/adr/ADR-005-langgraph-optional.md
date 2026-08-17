# ADR-005: LangGraph-Optional Orchestrator

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
The [`Orchestrator`](file:///f:/AI%20Automation/Projects/Zero/zero_core/orchestrator.py) is the central state coordinator for task routing and execution dispatch. The long-term architecture roadmap plans to use LangGraph for multi-node graph orchestration, cyclical self-correction, and human-in-the-loop checkpointing.

## Problem
In early milestones (M1–M4), the orchestration workflow consists of a single routing step (`route -> END`). Requiring a hard dependency on LangGraph during initial development introduces installation overhead and potential environment incompatibilities without providing immediate structural value.

## Decision
LangGraph is implemented as **optional**:
- [`orchestrator.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/orchestrator.py) attempts to import `langgraph.graph.StateGraph`.
- If available, it compiles and runs a `StateGraph(ZeroState)`.
- If unavailable, it executes a lightweight, 3-line pure-Python state transition fallback (`_run_fallback`).

## Why We Made the Decision
1. **Frictionless Onboarding & Testing**: Allows unit test suites and basic CLI usage to run anywhere without requiring `langgraph` or external compilation toolchains.
2. **Smooth Upgrade Path**: When multi-node graph flows (memory lookup, approval checkpoints, retry loops) are introduced in M6–M8, `langgraph` can be activated without altering the public `Orchestrator.run()` / `Orchestrator.execute()` interface signatures.
3. **Resilience**: Protects the core system from breaking if optional package installations fail.

## Alternatives Considered
- **Strictly Require LangGraph**: Rejected because single-node graph logic does not justify a mandatory dependency in early phases.
- **Custom-Built Graph Engine**: Rejected to avoid building and maintaining a proprietary DAG engine when LangGraph is already chosen as the future standard.

## Consequences
- **Positive**: Zero mandatory third-party runtime dependencies for core routing tests; backward-compatible transition path.
- **Negative**: Two execution branches exist internally in `orchestrator.py` until LangGraph is made mandatory in later phases.
