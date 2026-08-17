"""Wires the registry + orchestrator together. This is what a future CLI,
FastAPI app, or Telegram bot handler imports — nothing else in zero_core
should need to know how these pieces are constructed.
"""

from __future__ import annotations

from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
from zero_core.native_agents import ALL_NATIVE_AGENTS
from zero_core.orchestrator import Orchestrator


def build_registry() -> AgentRegistry:
    adapter = AgencyAgentsAdapter()
    return AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)


def build_orchestrator() -> Orchestrator:
    return Orchestrator(registry=build_registry())


if __name__ == "__main__":
    # Manual smoke test: run this on your machine (where the real
    # Agency-agents clone sits next to Zero/) to sanity-check indexing.
    #   python -m zero_core.bootstrap
    registry = build_registry()
    agency_count = len(registry.list_agency())
    native_count = len(registry.list_native())
    print(f"Indexed {agency_count} Agency-agents specialists, {native_count} ZERO-native agents.")
    if agency_count == 0:
        print(
            "0 Agency-agents specialists found — check that AGENCY_AGENTS_PATH "
            "points at your local clone (defaults to the sibling 'Agency-agents' folder)."
        )

    orch = build_orchestrator()
    for sample_task in [
        "What did I spend on subscriptions last month?",
        "What's my current trading position?",
        "Review this React component for accessibility issues",
        "Design a threat model for the new API",
    ]:
        decision = orch.run(sample_task)
        outcome = orch.execute(sample_task)
        print("\n" + decision.explain())
        if outcome.needs_llm:
            print("-> hand off to an LLM call with the persona above (not run here)")
        else:
            print(f"-> {outcome.answer}")
