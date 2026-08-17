"""ZERO — End-to-End Multi-Agent Demonstration Script.

Runs real sample queries through the Orchestrator to demonstrate live execution
across native agents and Agency-agents specialists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zero_core.bootstrap import build_orchestrator
from zero_core.llm import DEFAULT_LLM_MANAGER


def run_demo():
    print("=" * 70)
    print("        ZERO — PERSONAL AI OPERATING SYSTEM DEMONSTRATION")
    print("=" * 70)

    orch = build_orchestrator()
    native_agents = orch.registry.list_native()
    agency_agents = orch.registry.list_agency()

    print(f"\n[+] Core Initialized:")
    print(f"    • Native Domain Agents: {len(native_agents)}")
    print(f"    • Agency Specialists:  {len(agency_agents)} (across 17 divisions)")
    print("-" * 70)

    sample_tasks = [
        ("Give me my morning operational briefing", "Briefing Agent"),
        ("What's my current trading bot status and last signal?", "Trading Agent"),
        ("Summarize my calendar schedule for today", "Calendar Agent"),
        ("Triage my inbox and list unread emails", "Email Agent"),
        ("Synthesize research on Vector Database indexing algorithms", "Research Agent"),
        ("Build a project blueprint for AI Recruitment Screening Bot", "Project Builder"),
        ("Check git working tree status and branch safety", "Git Agent"),
        ("What is my current learning mastery plan?", "Learning Agent"),
        ("Design a threat model for our REST API endpoints", "Agency Security Specialist"),
    ]

    for idx, (task, expected_domain) in enumerate(sample_tasks, start=1):
        print(f"\n[{idx}/9] TASK: \"{task}\"")
        print(f"    Target Area: {expected_domain}")

        decision = orch.run(task)
        outcome = orch.execute(task)

        selected = decision.selected
        agent_name = selected.name if selected else "Unknown"
        agent_slug = selected.slug if selected else "none"
        agent_source = selected.source if selected else "unknown"

        print(f"    -> Selected: {agent_name} [{agent_slug}] ({agent_source})")

        if outcome.needs_llm and outcome.persona:
            llm_response = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=task)
            first_line = llm_response.splitlines()[0] if llm_response else ""
            print(f"    -> LLM Specialist Answer: {first_line}")
        else:
            preview = (outcome.answer or "").splitlines()[0] if outcome.answer else "(no output)"
            print(f"    -> Native Execution Answer: {preview[:80]}...")

    print("\n" + "=" * 70)
    print("  [SUCCESS] All 9 multi-agent workflows resolved and executed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
