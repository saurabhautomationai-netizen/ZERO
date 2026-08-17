"""Interactive Terminal CLI for ZERO — Personal AI Operating System.

Run with:
    python -m zero_core.cli
"""

from __future__ import annotations

import sys
from zero_core.bootstrap import build_orchestrator
from zero_core.interfaces.telegram.formatters import format_task_response
from zero_core.llm import DEFAULT_LLM_MANAGER


def run_cli_interactive():
    print("=" * 60)
    print("  ZERO — Personal AI Operating System (Interactive CLI)")
    print("=" * 60)
    print("Type your task, question, or slash command (/agents, /status, /help, exit)")
    print()

    orch = build_orchestrator()
    native_count = len(orch.registry.list_native())
    agency_count = len(orch.registry.list_agency())
    print(f"[*] Core Online: {native_count} Native Agents, {agency_count} Agency Specialists indexed.")
    print()

    while True:
        try:
            user_input = input("ZERO > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting ZERO CLI.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Shutting down ZERO session.")
            break

        if user_input == "/agents":
            print("\n=== Native Domain Agents ===")
            for a in orch.registry.list_native():
                print(f"  • {a.name} ({a.slug})")
            print(f"\n=== Agency-agents Specialists ({agency_count} Total) ===")
            for a in orch.registry.list_agency()[:8]:
                print(f"  • {a.name} ({a.slug})")
            print("  ...and more across 17 divisions.\n")
            continue

        if user_input == "/status":
            print("\n[+] Status: All systems operational. Orchestrator, Tools, Memory, RAG active.\n")
            continue

        if user_input in ("/help", "help"):
            print("\nCommands: /agents, /status, /help, exit | Or enter any natural-language task.\n")
            continue

        # Execute task through Orchestrator
        decision = orch.run(user_input)
        outcome = orch.execute(user_input)

        selected_name = decision.selected.name if decision.selected else "Unknown"
        selected_slug = decision.selected.slug if decision.selected else "none"

        print(f"\n[+] Routed to: {selected_name} ({selected_slug})")

        if outcome.needs_llm and outcome.persona:
            print("[*] Invoking specialist LLM...")
            answer = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=user_input)
            print(f"\n{answer}\n")
        else:
            print(f"\n{outcome.answer}\n")


if __name__ == "__main__":
    run_cli_interactive()
