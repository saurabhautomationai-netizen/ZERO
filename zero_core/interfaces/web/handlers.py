"""Pure request-handling logic for the web interface.

Deliberately has NO import of fastapi (or any web framework) — this module
is fully unit-testable without that dependency installed at all, and
app.py (the actual FastAPI route wiring) stays a thin, mostly-untested-by-
necessity shim that just calls into here. This is the same "interfaces
carry no business logic" rule documented in this folder's README, applied.

Known Phase 1 inefficiency, left as-is on purpose rather than
prematurely optimized: every call rebuilds the registry from scratch,
which re-scans and re-parses all 269 Agency-agents files from disk. Fine
for occasional personal use; if this ever sits behind real request volume,
cache the registry (e.g. FastAPI lifespan + app.state, or
functools.lru_cache with an explicit invalidation hook for
`git pull`-ed updates to the Agency-agents clone) — don't add that
complexity before it's actually needed.
"""

from __future__ import annotations

from typing import Any, Optional

from zero_core.agent_registry import AgentSpec
from zero_core.bootstrap import build_orchestrator, build_registry


def _spec_to_dict(spec: Optional[AgentSpec]) -> Optional[dict[str, Any]]:
    if spec is None:
        return None
    return {
        "name": spec.name,
        "slug": spec.slug,
        "source": spec.source,
        "division": spec.division,
        "description": spec.description,
    }


from zero_core.llm import DEFAULT_LLM_MANAGER


def handle_task(task: str, auto_invoke_llm: bool = True) -> dict[str, Any]:
    if not task or not task.strip():
        return {"error": "task must be a non-empty string"}

    orch = build_orchestrator()
    decision = orch.run(task)
    outcome = orch.execute(task)

    answer = outcome.answer
    if outcome.needs_llm and outcome.persona and auto_invoke_llm and answer is None:
        answer = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=task)

    return {
        "task": task,
        "selected": _spec_to_dict(decision.selected),
        "alternatives": [_spec_to_dict(a) for a in decision.alternatives],
        "needs_llm": outcome.needs_llm,
        "answer": answer,
        "persona": outcome.persona if outcome.needs_llm else None,
    }


def handle_list_agents(division: Optional[str] = None) -> dict[str, Any]:
    registry = build_registry()
    agency = registry.list_agency(division=division)
    return {
        "native": [_spec_to_dict(a) for a in registry.list_native()],
        "agency": [_spec_to_dict(a) for a in agency],
        "agency_count": len(agency),
    }


def handle_get_agent(slug: str) -> Optional[dict[str, Any]]:
    registry = build_registry()
    return _spec_to_dict(registry.get(slug))
