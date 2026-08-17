"""Orchestrator skeleton.

Phase 1 scope: prove the routing contract end-to-end (task in -> Agent
Registry decides native vs. Agency-agents specialist -> decision out).
It does NOT yet execute the selected agent, hold conversation state across
turns, or touch Memory/RAG — those are later phases once this contract is
verified against real usage.

Built on LangGraph where available (matches your stated stack), but degrades
to a tiny pure-Python state machine if langgraph isn't installed, so this
module — and its tests — never hard-fail on a missing optional dependency.
Swap `_run_fallback` for the LangGraph-compiled graph transparently once
you `pip install langgraph` in this project's venv.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict

from zero_core.agent_registry import AgentRegistry, AgentSpec, RegistryMatch
from zero_core.executors import ExecutionResult, execute as _execute_spec

try:
    from langgraph.graph import StateGraph, END
    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover - exercised in envs without langgraph
    _HAS_LANGGRAPH = False


class ZeroState(TypedDict, total=False):
    task: str
    match: RegistryMatch
    selected: Optional[AgentSpec]


@dataclass
class OrchestratorResult:
    task: str
    selected: Optional[AgentSpec]
    alternatives: list[AgentSpec] = field(default_factory=list)

    def explain(self) -> str:
        if self.selected is None:
            return f"No specialist matched: {self.task!r}"
        alt = ", ".join(a.name for a in self.alternatives) or "none"
        return (
            f"Task: {self.task!r}\n"
            f"Selected: {self.selected.name} [{self.selected.source}/{self.selected.division}]\n"
            f"Alternatives considered: {alt}"
        )


class Orchestrator:
    """ZERO's routing brain. Owns the decision; does not execute agents (yet)."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._graph = self._build_graph() if _HAS_LANGGRAPH else None

    # -- LangGraph path -----------------------------------------------------
    def _build_graph(self):  # pragma: no cover - requires langgraph installed
        def route_node(state: ZeroState) -> ZeroState:
            match = self.registry.resolve(state["task"])
            return {**state, "match": match, "selected": match.best}

        graph = StateGraph(ZeroState)
        graph.add_node("route", route_node)
        graph.set_entry_point("route")
        graph.add_edge("route", END)
        return graph.compile()

    # -- Fallback path (no langgraph installed) -----------------------------
    def _run_fallback(self, task: str) -> ZeroState:
        match = self.registry.resolve(task)
        return {"task": task, "match": match, "selected": match.best}

    def run(self, task: str) -> OrchestratorResult:
        if self._graph is not None:  # pragma: no cover
            final_state = self._graph.invoke({"task": task})
        else:
            final_state = self._run_fallback(task)

        match: RegistryMatch = final_state["match"]
        return OrchestratorResult(
            task=task,
            selected=final_state["selected"],
            alternatives=[c for c in match.candidates if c != final_state["selected"]],
        )

    def execute(self, task: str) -> ExecutionResult:
        """`run()` only decides. This actually produces an answer where ZERO
        can (native agents backed by a real adapter) and hands off a persona
        for an external LLM call otherwise (Agency-agents specialists) —
        see zero_core/executors.py for why those two cases are handled
        differently rather than both being faked into "an answer."
        """
        decision = self.run(task)
        if decision.selected is None:
            return ExecutionResult(spec=None, answer="No specialist matched this task.", needs_llm=False)
        return _execute_spec(decision.selected, task, agency_adapter=self.registry.agency)
