"""Dynamic Discovery Planner for ZERO Engineering Organization.

Analyzes repository structure, file extensions, detected frameworks, and requested scope
to dynamically construct a tailored, read-only Task DAG. Avoids hardcoded project IDs by
evaluating capability and department requirements directly from codebase reality.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, TaskItem
from zero_core.engineering.resolver import EngineeringRequest

logger = logging.getLogger("zero.engineering.discovery.planner")


@dataclass
class DiscoveryTaskPlan:
    """A single specialized read-only task in the dynamic discovery DAG."""
    task_id: str
    title: str
    description: str
    assigned_worker: str
    subsystem_filter: str
    department: str
    target_files: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)


@dataclass
class ReadOnlyDiscoveryDAG:
    """Dynamic DAG containing tailored read-only tasks for existing project audit."""
    project_id: str
    project_name: str
    tasks: List[DiscoveryTaskPlan] = field(default_factory=list)
    detected_subsystems: List[str] = field(default_factory=list)

    def to_task_items(self) -> List[TaskItem]:
        """Converts discovery plan into standard TaskItem objects for execution."""
        return [
            TaskItem(
                task_id=t.task_id,
                milestone_id="M_DEEP_DISCOVERY",
                title=t.title,
                description=t.description,
                assigned_worker=t.assigned_worker,
                acceptance_criteria=t.acceptance_criteria,
            )
            for t in self.tasks
        ]


class DiscoveryPlanner:
    """Intelligent manager constructing dynamic discovery DAGs based on repository evidence."""

    def plan_discovery(
        self,
        manifest: ProjectManifest,
        request: Optional[EngineeringRequest] = None,
    ) -> ReadOnlyDiscoveryDAG:
        """Dynamically determines the required discovery tasks based on repository evidence."""
        repo_path = Path(manifest.repository_path)
        detected_subsystems: Set[str] = set()

        # 1. Inspect repository file presence safely
        if repo_path.exists() and repo_path.is_dir():
            for root, dirs, files in os.walk(str(repo_path)):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", ".venv", "__pycache__")]
                for fname in files:
                    f_lower = fname.lower()
                    ext = Path(fname).suffix.lower()

                    if ext in (".sql", ".prisma"):
                        detected_subsystems.add("database")
                    elif ext == ".json" and any(w in f_lower for w in ("workflow", "tracker", "n8n", "bridge", "ingestion")):
                        detected_subsystems.add("automation")
                    elif ext in (".txt", ".prompt") and any(p in f_lower for p in ("prompt", "claude", "agent", "instruction", "pft")):
                        detected_subsystems.add("prompts")
                    elif ext in (".py", ".ts", ".js", ".go") and not f_lower.startswith("test_") and not f_lower.endswith("_test.py"):
                        detected_subsystems.add("code")
                    elif ext in (".html", ".css", ".tsx", ".jsx") or "dashboard" in f_lower or "streamlit" in f_lower:
                        detected_subsystems.add("uiux")
                    elif f_lower.startswith("test_") or f_lower.endswith("_test.py") or "test" in root.lower():
                        detected_subsystems.add("tests")

        # 2. Check request scope hints
        if request and request.raw_instruction:
            req_lower = request.raw_instruction.lower()
            if any(k in req_lower for k in ("n8n", "workflow", "webhook")):
                detected_subsystems.add("automation")
            if any(k in req_lower for k in ("database", "schema", "table", "sql")):
                detected_subsystems.add("database")
            if any(k in req_lower for k in ("prompt", "ai", "llm", "agent instruction")):
                detected_subsystems.add("prompts")
            if any(k in req_lower for k in ("ui", "ux", "dashboard", "frontend")):
                detected_subsystems.add("uiux")

        tasks: List[DiscoveryTaskPlan] = []

        # Task 1: Overarching Architecture & Structure Audit (Always included)
        tasks.append(
            DiscoveryTaskPlan(
                task_id="t_disc_arch",
                title=f"Architecture & Repository Structure Audit for {manifest.project_name}",
                description="Inspect root structure, dependency manifests, and architectural organization in read-only mode.",
                assigned_worker="worker_project_builder",
                subsystem_filter="architecture",
                department="product",
                acceptance_criteria=["Catalog entry points", "Determine framework dependencies", "Assess modular boundaries"],
            )
        )

        # Task 2: Automation & Workflow Audit (if workflows detected)
        if "automation" in detected_subsystems:
            tasks.append(
                DiscoveryTaskPlan(
                    task_id="t_disc_auto",
                    title=f"Automation & Workflow Graph Audit for {manifest.project_name}",
                    description="Inspect workflow JSON definitions, node graphs, trigger webhooks, and channel integrations in read-only mode.",
                    assigned_worker="worker_automation",
                    subsystem_filter="automation",
                    department="automation",
                    acceptance_criteria=["Extract node counts and types", "Map triggers and webhook paths", "Identify connected external channels"],
                )
            )

        # Task 3: Database & Relational Schema Audit (if database/SQL detected)
        if "database" in detected_subsystems:
            tasks.append(
                DiscoveryTaskPlan(
                    task_id="t_disc_db",
                    title=f"Database Schema & Entity Relationship Audit for {manifest.project_name}",
                    description="Inspect SQL DDL definitions, tables, indexes, views, and constraints in read-only mode.",
                    assigned_worker="worker_database_audit",
                    subsystem_filter="database",
                    department="engineering",
                    acceptance_criteria=["Catalog defined tables and column schemas", "Count indexes and triggers", "Map entity relationships"],
                )
            )

        # Task 4: AI Prompts & Domain Specifications Audit (if prompts detected)
        if "prompts" in detected_subsystems:
            tasks.append(
                DiscoveryTaskPlan(
                    task_id="t_disc_prompt",
                    title=f"AI Prompt & Domain Specification Audit for {manifest.project_name}",
                    description="Inspect AI system prompts, operational playbooks, and domain guidelines in read-only mode.",
                    assigned_worker="worker_research_agent",
                    subsystem_filter="prompts",
                    department="research",
                    acceptance_criteria=["Analyze system prompt instructions", "Extract business domain constraints", "Verify prompt-to-code alignment"],
                )
            )

        # Task 5: Source Code & Technical Debt Audit (if code detected)
        if "code" in detected_subsystems:
            tasks.append(
                DiscoveryTaskPlan(
                    task_id="t_disc_code",
                    title=f"Source Code Implementation & Technical Debt Audit for {manifest.project_name}",
                    description="Inspect core code modules, architectural smells, code quality, and technical debt in read-only mode.",
                    assigned_worker="worker_coding_agent",
                    subsystem_filter="code",
                    department="engineering",
                    acceptance_criteria=["Audit code structure", "Catalog technical debt and code smells", "Assess refactoring needs"],
                )
            )

        # Task 6: UI/UX & Dashboard Asset Audit (if UI assets detected)
        if "uiux" in detected_subsystems:
            tasks.append(
                DiscoveryTaskPlan(
                    task_id="t_disc_uiux",
                    title=f"UI/UX & Dashboard Interface Audit for {manifest.project_name}",
                    description="Inspect frontend components, dashboards, templates, and user experience touchpoints in read-only mode.",
                    assigned_worker="worker_uiux_designer",
                    subsystem_filter="uiux",
                    department="design",
                    acceptance_criteria=["Audit UI templates and dashboard pages", "Verify user interface readiness"],
                )
            )

        logger.info(
            "DiscoveryPlanner created dynamic DAG for '%s' with %d tasks across subsystems: %s",
            manifest.project_name,
            len(tasks),
            list(detected_subsystems),
        )

        return ReadOnlyDiscoveryDAG(
            project_id=manifest.project_id,
            project_name=manifest.project_name,
            tasks=tasks,
            detected_subsystems=list(detected_subsystems),
        )
