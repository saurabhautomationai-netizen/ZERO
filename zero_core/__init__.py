"""ZERO Core — Personal AI Operating System.

This package is the connective tissue described in the ZERO architecture:

    ZERO
     |
     +-- Orchestrator      (zero_core.orchestrator)
     +-- Memory            (zero_core.memory)          [Phase 2: pgvector/Supabase]
     +-- Agent Registry     (zero_core.agent_registry)
          |
          +-- ZERO Native Agents   (zero_core.native_agents)
          +-- Agency-agents        (adapter over the local Agency-agents clone)

Phase 1 (this scaffold) delivers a working Agent Registry + Agency-agents
Adapter and an Orchestrator skeleton that can route a task to either a
ZERO-native agent or an Agency-agents specialist. It intentionally does
NOT reimplement Trading bot or Personal Finance Tracker — see
zero_core/native_agents.py and ARCHITECTURE.md for the integration plan.
"""

__version__ = "0.1.0-phase1"
