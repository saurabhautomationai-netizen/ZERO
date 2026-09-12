"""Department Registry for ZERO Engineering Organization.

Categorizes native agents, agency specialists, external workers, and tools
into cohesive functional engineering departments.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zero.engineering.departments.registry")


@dataclass
class DepartmentSpec:
    """Descriptor for an engineering or operational department within ZERO."""
    department_id: str
    name: str
    description: str
    lead_worker_id: Optional[str] = None
    member_worker_ids: List[str] = field(default_factory=list)
    native_agents: List[str] = field(default_factory=list)
    agency_divisions: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    policies: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DepartmentRegistry:
    """Central registry organizing workers and specialists into departments."""

    def __init__(self):
        self._departments: Dict[str, DepartmentSpec] = {}
        self.seed_defaults()

    def register(self, dept: DepartmentSpec) -> None:
        """Registers or updates a department definition."""
        self._departments[dept.department_id] = dept
        logger.info("Registered department: %s (%s)", dept.name, dept.department_id)

    def get(self, department_id: str) -> Optional[DepartmentSpec]:
        """Retrieves a department by its ID."""
        return self._departments.get(department_id)

    def list_departments(self) -> List[DepartmentSpec]:
        """Returns all registered departments."""
        return list(self._departments.values())

    def find_for_task(self, task_description: str) -> Optional[DepartmentSpec]:
        """Heuristically maps a task description to the most appropriate department."""
        t = task_description.lower()

        keywords_map = {
            "engineering": ["code", "refactor", "bug", "python", "fastapi", "backend", "endpoint", "git", "commit"],
            "design": ["ui", "ux", "design", "wireframe", "css", "layout", "mockup", "theme", "color", "screen"],
            "product": ["srs", "requirements", "product", "milestone", "roadmap", "user story", "scaffold"],
            "research": ["research", "literature", "benchmark", "market analysis", "paper", "comparison"],
            "qa": ["test", "pytest", "unit test", "integration test", "e2e", "qa", "coverage", "verify"],
            "automation": ["workflow", "n8n", "webhook", "automation", "trigger", "ingestion", "bridge", "node"],
            "security": ["security", "audit", "secret", "vulnerability", "auth", "rbac", "permission", "cve"],
            "database": ["database", "sql", "migration", "postgres", "supabase", "table", "schema", "ddl", "index"],
            "devops": ["docker", "container", "ci/cd", "pipeline", "compose", "cloud run", "kubernetes"],
            "deployment": ["deploy", "health check", "release", "production", "monitoring", "server"],
            "sales": ["lead", "sales", "crm", "pipeline", "client", "deal", "pitch"],
            "marketing": ["ad", "meta ad", "social", "campaign", "instagram", "copy", "branding"],
            "finance": ["finance", "expense", "budget", "cost", "spending", "runway", "invoice"],
            "trading": ["trading", "trade", "mt5", "position", "candle", "stop loss", "forex", "crypto"],
            "operations": ["patrol", "loop", "manifest", "audit", "checkpoint", "orchestration"],
        }

        best_dept = None
        best_score = 0

        for dept_id, kws in keywords_map.items():
            score = sum(1 for kw in kws if kw in t)
            if score > best_score:
                best_score = score
                best_dept = dept_id

        return self.get(best_dept) if best_dept else self.get("engineering")

    def seed_defaults(self) -> None:
        """Populates the standard ZERO organization departments."""
        defaults = [
            DepartmentSpec(
                department_id="engineering",
                name="Software Engineering",
                description="Core application development, architecture implementation, refactoring, and code generation.",
                lead_worker_id="worker_coding_agent",
                member_worker_ids=["worker_coding_agent", "worker_project_builder", "worker_antigravity", "worker_chatgpt"],
                native_agents=["native/coding-agent", "native/git-agent", "native/loop-engineering-agent"],
                agency_divisions=["engineering"],
                tools=["filesystem", "workspace_tools"],
            ),
            DepartmentSpec(
                department_id="automation",
                name="Automation & Workflows",
                description="n8n workflow integration, webhook pipeline orchestration, trigger event architecture, and workflow reverse engineering.",
                lead_worker_id="worker_automation",
                member_worker_ids=["worker_automation"],
                native_agents=["native/automation-agent"],
                agency_divisions=["automation"],
                tools=["filesystem", "webhook_tools"],
            ),
            DepartmentSpec(
                department_id="design",
                name="UI/UX & Product Design",
                description="User experience architecture, visual design systems, interactive prototypes, and accessibility.",
                lead_worker_id="worker_uiux_designer",
                member_worker_ids=["worker_uiux_designer"],
                native_agents=[],
                agency_divisions=["design"],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="product",
                name="Product Management",
                description="Feature scoping, software requirements specification (SRS), roadmap definition, and acceptance criteria.",
                lead_worker_id="worker_project_builder",
                member_worker_ids=["worker_project_builder", "worker_chatgpt"],
                native_agents=["native/project-builder"],
                agency_divisions=["product", "project-management"],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="research",
                name="Research & Technical Intelligence",
                description="Autonomous literature synthesis, competitor benchmarking, technical analysis, and citation tracking.",
                lead_worker_id="worker_research_agent",
                member_worker_ids=["worker_research_agent", "worker_chatgpt"],
                native_agents=["native/research-agent"],
                agency_divisions=["academic"],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="qa",
                name="Quality Assurance & Testing",
                description="Automated unit, integration, and E2E testing, reality checks, coverage metrics, and phase validation.",
                lead_worker_id="worker_coding_agent",
                member_worker_ids=["worker_coding_agent", "worker_chatgpt"],
                native_agents=["native/coding-agent"],
                agency_divisions=["testing"],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="security",
                name="Cybersecurity & Governance",
                description="Static vulnerability scanning, secret leak detection, least-privilege RBAC auditing, and compliance verification.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=[],
                agency_divisions=["security"],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="devops",
                name="DevOps & Infrastructure",
                description="Docker containerization, CI/CD pipeline automation, environment provisioning, and cloud infrastructure.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=["native/deployment-agent"],
                agency_divisions=["engineering"],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="deployment",
                name="Release & Deployment",
                description="Release candidate verification, database migration execution, deployment health checks, and rollback controls.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=["native/deployment-agent"],
                agency_divisions=[],
                tools=["filesystem"],
            ),
            DepartmentSpec(
                department_id="sales",
                name="Sales & CRM",
                description="Inbound lead qualification, pipeline forecasting, proposal drafting, and client follow-ups.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=["native/sales-agent"],
                agency_divisions=["sales"],
                tools=[],
            ),
            DepartmentSpec(
                department_id="marketing",
                name="Marketing & Growth",
                description="Paid media strategy, ad creative generation, copywriting, and social media campaigns.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=[],
                agency_divisions=["marketing", "paid-media"],
                tools=[],
            ),
            DepartmentSpec(
                department_id="finance",
                name="Finance & Ledger",
                description="Transaction tracking, subscription audit, budget monitoring, and financial runway forecasting.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=["native/finance-agent"],
                agency_divisions=["finance"],
                tools=["finance_tools"],
            ),
            DepartmentSpec(
                department_id="trading",
                name="Algorithmic Trading",
                description="MetaTrader 5 live integration, SMC market confluence analysis, risk guardrails, and strategy auditing.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=["native/trading-agent", "native/trading-coach"],
                agency_divisions=[],
                tools=["trading_tools"],
            ),
            DepartmentSpec(
                department_id="operations",
                name="Operations & Autonomous Patrol",
                description="Multi-project auditing, autonomous proposal generation, log pruning, and project state governance.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=["native/loop-engineering-agent"],
                agency_divisions=["project-management"],
                tools=["project_tools"],
            ),
            DepartmentSpec(
                department_id="personal_productivity",
                name="Personal Productivity & Briefings",
                description="Gmail triage, calendar scheduling, morning/evening briefings, news synthesis, and learning tracks.",
                lead_worker_id=None,
                member_worker_ids=[],
                native_agents=[
                    "native/email-agent",
                    "native/calendar-agent",
                    "native/briefing-agent",
                    "native/learning-agent",
                    "native/news-agent",
                ],
                agency_divisions=[],
                tools=[],
            ),
        ]

        for dept in defaults:
            self.register(dept)


# Global singleton instance
DEFAULT_DEPARTMENT_REGISTRY = DepartmentRegistry()
