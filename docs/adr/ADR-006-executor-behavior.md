# ADR-006: Executor Behavior: Answer or Persona Handoff

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
After the Orchestrator selects an agent for a given task, the system must execute the task. In ZERO, three distinct agent categories exist:
1. Native agents with implemented data adapters (Finance, Trading).
2. Native agents without implemented adapters (Trading Coach, Email, Calendar stubs).
3. Upstream specialist personas from Agency-agents (269 personas).

## Problem
How should the execution layer ([`zero_core/executors.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/executors.py)) handle execution requests across these diverse agent types without falsifying data, fabricating LLM answers, or embedding expensive model client calls directly in the core engine?

## Decision
[`executors.py:execute()`](file:///f:/AI%20Automation/Projects/Zero/zero_core/executors.py) produces an [`ExecutionResult`](file:///f:/AI%20Automation/Projects/Zero/zero_core/executors.py) with explicit, honest semantics:
- **Native Agents with Adapters**: Executed via deterministic Python functions against real data sources. Returns `needs_llm=False`, `answer="<real data>"`, `persona=None`.
- **Native Agents without Adapters**: Returns `needs_llm=False`, `answer="<Agent> is a planned ZERO-native agent, not implemented yet"`, `persona=None`.
- **Agency-agents Specialists**: Core does NOT execute an LLM call. Returns `needs_llm=True`, `answer=None`, `persona="<full markdown persona text>"`.

## Why We Made the Decision
1. **Honest Execution**: Never fakes or hallucinates an LLM response within core routing code.
2. **Decoupled Architecture**: Keeps `zero_core` free from LLM vendor SDK dependencies (OpenAI, Anthropic, Google GenAI), leaving the model invocation choice to the consumer interface (Web, CLI, Telegram).
3. **Deterministic Testing**: Every executor pathway is 100% testable without live API keys or mock LLM token streams.

## Alternatives Considered
- **Direct LLM Client in Core**: Rejected because it couples core business logic to specific AI providers and requires active API keys during unit testing.
- **Simulate LLM Responses with Mock Strings**: Rejected because false mock answers mislead downstream consumers and obscure integration readiness.

## Consequences
- **Positive**: Clean separation between core orchestration and consumer-side LLM invocation; robust and honest operational status.
- **Negative**: User-facing interfaces (e.g. FastAPI / Telegram) are responsible for implementing the model call when `needs_llm=True`.
