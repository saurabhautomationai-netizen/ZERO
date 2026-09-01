"""Project Knowledge System for ZERO (Master Architecture Project Knowledge Layer).

Indexes and queries architectural context, tech stack, roadmap, and status across projects.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProjectProfile:
    """Represents architectural and operational knowledge for a tracked project."""
    project_id: str
    name: str
    purpose: str
    tech_stack: List[str]
    current_status: str
    architecture_overview: str
    roadmap: List[str] = field(default_factory=list)
    known_bugs_todos: List[str] = field(default_factory=list)
    git_repo_or_path: str = ""
    deployment_info: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"# Project: {self.name} [{self.current_status}]",
            f"**Purpose**: {self.purpose}",
            f"**Tech Stack**: {', '.join(self.tech_stack)}",
            f"**Path**: `{self.git_repo_or_path}`",
            "",
            "## Architecture Overview",
            self.architecture_overview,
        ]
        if self.roadmap:
            lines.append("\n## Roadmap")
            for r in self.roadmap:
                lines.append(f"- {r}")

        if self.known_bugs_todos:
            lines.append("\n## Known Bugs & TODOs")
            for b in self.known_bugs_todos:
                lines.append(f"- {b}")

        if self.deployment_info:
            lines.append(f"\n**Deployment**: {self.deployment_info}")

        return "\n".join(lines)


class ProjectKnowledgeStore:
    """Stores and queries structured project knowledge."""

    def __init__(self, persistence_file: Optional[Path] = None):
        self.persistence_file = persistence_file
        self._projects: Dict[str, ProjectProfile] = {}
        self._seed_default_projects()

    def _seed_default_projects(self) -> None:
        """Pre-seeds the knowledge store with known workspace projects."""
        self.add_project(
            ProjectProfile(
                project_id="zero",
                name="ZERO — Personal AI Operating System",
                purpose="Single command center coordinating native agents, Agency-agents, and automations.",
                tech_stack=["Python", "FastAPI", "LangGraph", "pgvector", "Docker", "Pytest"],
                current_status="Phase 1-3 Core Complete (106 tests passing)",
                architecture_overview="Decoupled state machines, unified Agent Registry, Tool Registry, Approval guardrails, Vector RAG.",
                roadmap=[
                    "M1-M8 Core, Tools, Memory, RAG (Done)",
                    "M11-M18 Native Domain Agents (Done)",
                    "M19-M21 Multi-channel Interfaces & Deployment (Done)",
                ],
                git_repo_or_path="f:/AI Automation/Projects/Zero",
                deployment_info="Docker compose with FastAPI app and pgvector PostgreSQL.",
            )
        )

        self.add_project(
            ProjectProfile(
                project_id="trading_bot",
                name="Trading Bot (MT5 Live System)",
                purpose="Live automated trading bot executing SMC and momentum strategies on MT5.",
                tech_stack=["Python", "MetaTrader5", "Pandas", "TA-Lib"],
                current_status="Live / Active Execution",
                architecture_overview="Standalone MT5 bridge, risk validator, live buy/sell runners, signal state JSON persistence.",
                roadmap=["Continuous strategy optimization", "Trading Coach RAG integration"],
                known_bugs_todos=["Monitor signal stale counts on market close"],
                git_repo_or_path="f:/AI Automation/Projects/Trading bot",
                deployment_info="Local Windows MT5 Desktop runtime.",
            )
        )

        self.add_project(
            ProjectProfile(
                project_id="finance_tracker",
                name="Smart Finance AI Tracker",
                purpose="118-node n8n workflow for multi-modal personal finance management.",
                tech_stack=["n8n", "PostgreSQL", "Google Sheets", "Telegram Bot"],
                current_status="Operational",
                architecture_overview="Webhook intake across voice/image/PDF/XLSX into PostgreSQL public.transactions, budget alerts, and analytics.",
                roadmap=["ZERO Finance Agent read-only integration via zero_finance_reader role"],
                known_bugs_todos=["Rotate plaintext API keys from .mcp.json"],
                git_repo_or_path="f:/AI Automation/Projects/Smart Finance AI Tracker",
                deployment_info="n8n cloud/local instance + PostgreSQL.",
            )
        )

        self.add_project(
            ProjectProfile(
                project_id="talent_lead_gen_agent",
                name="Autonomous Candidate Lead Generation Agent",
                purpose="Autonomous talent sourcing and lead enrichment engine working alongside HR Recruitment AI Assistant.",
                tech_stack=["Python", "FastAPI", "Supabase", "Gemini 3.6", "Pytest"],
                current_status="Built & Operational (8 tests passing)",
                architecture_overview="Webhook receiver (/api/v1/trigger-sourcing), recruitment-specialist evaluator, GitHub scraper, Supabase candidates ingestion, and Telegram alerts.",
                roadmap=["M1 Architecture & Core (Done)", "M2 Live Supabase Integration (Done)", "M3 Multi-platform scrapers (Done)"],
                git_repo_or_path="f:/AI Automation/Projects/Talent Lead Gen Agent",
                deployment_info="FastAPI service on port 8005 with shared Supabase database.",
            )
        )

        self.add_project(
            ProjectProfile(
                project_id="agency_agents",
                name="Agency-agents Specialist Library",
                purpose="269 specialist personas across 17 industry divisions.",
                tech_stack=["Markdown", "YAML Frontmatter", "Shell Linter"],
                current_status="Indexed (Live Filesystem Index)",
                architecture_overview="Stateless markdown system prompt personas dynamically discovered and resolved by ZERO.",
                git_repo_or_path="f:/AI Automation/Projects/Agency-agents",
                deployment_info="Local filesystem directory.",
            )
        )

    def add_project(self, profile: ProjectProfile) -> None:
        self._projects[profile.project_id] = profile

    def get_project(self, project_id: str) -> Optional[ProjectProfile]:
        if project_id in self._projects:
            return self._projects[project_id]
        from zero_core.engineering.resolver import CANONICAL_PROJECT_ALIASES
        # Bidirectional resolution between short knowledge keys and canonical manifest project_ids
        for alias, canon in CANONICAL_PROJECT_ALIASES.items():
            if canon == project_id and alias in self._projects:
                return self._projects[alias]
            if alias == project_id and canon in self._projects:
                return self._projects[canon]
        return None

    def search_projects(self, query: str) -> List[ProjectProfile]:
        q = query.lower()
        from zero_core.engineering.resolver import CANONICAL_PROJECT_ALIASES
        canon_target = CANONICAL_PROJECT_ALIASES.get(q)
        results = []
        for p in self._projects.values():
            if (
                q in p.name.lower()
                or q in p.purpose.lower()
                or q in p.project_id
                or (canon_target and canon_target == p.project_id)
            ):
                results.append(p)
        return results

    def answer_status_query(self, project_name: str) -> str:
        results = self.search_projects(project_name)
        if not results:
            return f"Project Knowledge: No project matching '{project_name}' found."
        return results[0].summary()


# Global singleton instance
DEFAULT_PROJECT_KNOWLEDGE = ProjectKnowledgeStore()
