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
    error: Optional[str] = None
    target_requested: Optional[str] = None

    def explain(self) -> str:
        if self.error == "AGENT_NOT_FOUND":
            return f"Agent not found: {self.target_requested!r} for task {self.task!r}"
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
    def _run_fallback(self, task: str, explicit_slug: Optional[str] = None) -> ZeroState:
        match = self.registry.resolve(task, explicit_slug=explicit_slug)
        return {"task": task, "match": match, "selected": match.best}

    def run(self, task: str, agent_slug: Optional[str] = None) -> OrchestratorResult:
        if self._graph is not None:  # pragma: no cover
            final_state = self._graph.invoke({"task": task, "explicit_slug": agent_slug})
        else:
            final_state = self._run_fallback(task, explicit_slug=agent_slug)

        match: RegistryMatch = final_state["match"]
        selected = final_state["selected"]

        from zero_core.observability import DEFAULT_LOGGER

        if match.error == "AGENT_NOT_FOUND":
            DEFAULT_LOGGER.warning(
                event_type="agent_not_found",
                message=f"Explicit target '{match.target_requested}' not found in registry",
                task=task[:100],
                target_requested=match.target_requested,
            )
            return OrchestratorResult(
                task=task,
                selected=None,
                alternatives=match.suggestions,
                error="AGENT_NOT_FOUND",
                target_requested=match.target_requested,
            )

        DEFAULT_LOGGER.info(
            event_type="routing_decision_created",
            message=f"Task routed to {selected.name if selected else 'None'}",
            task=task[:100],
            selected_agent=selected.slug if selected else None,
            routing_reason="Explicit target override" if match.is_explicit else "Direct intent match / keyword resolution",
        )

        return OrchestratorResult(
            task=task,
            selected=selected,
            alternatives=[c for c in match.candidates if c != selected],
        )

    def execute(self, task: str, agent_slug: Optional[str] = None) -> ExecutionResult:
        """`run()` only decides. This actually produces an answer where ZERO
        can (native agents backed by a real adapter) and hands off a persona
        for an external LLM call otherwise (Agency-agents specialists) —
        see zero_core/executors.py for why those two cases are handled
        differently rather than both being faked into "an answer."
        """
        decision = self.run(task, agent_slug=agent_slug)
        if decision.error == "AGENT_NOT_FOUND":
            suggestions_str = ""
            if decision.alternatives:
                suggestions_str = "\n\n**Did you mean one of these valid specialists?**\n" + "\n".join(
                    f"- **{s.name}** (`{s.slug}`)" for s in decision.alternatives[:5]
                )
            return ExecutionResult(
                spec=None,
                answer=(
                    f"⚠️ **AGENT_NOT_FOUND**: Explicit target `@{decision.target_requested}` does not exist in ZERO.\n"
                    f"ZERO will not silently route to another specialist when an explicit target is requested."
                    f"{suggestions_str}"
                ),
                needs_llm=False,
            )

        if decision.selected is None:
            return ExecutionResult(spec=None, answer="No specialist matched this task.", needs_llm=False)
        try:
            return _execute_spec(decision.selected, task, agency_adapter=self.registry.agency)
        except Exception as exc:
            from zero_core.observability import DEFAULT_LOGGER
            DEFAULT_LOGGER.error(
                event_type="task_execution_failed",
                message=f"Execution error for {decision.selected.name}: {exc}",
                selected_agent=decision.selected.slug,
                task=task[:100],
                error=str(exc),
            )
            return ExecutionResult(
                spec=decision.selected,
                answer=f"⚠️ Agent Execution Failed ({decision.selected.name}): {exc}",
                needs_llm=False,
            )
