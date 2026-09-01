"""Project knowledge and Git repository tools for ZERO Tool Registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from zero_core.agents.coding_agent import DEFAULT_CODING_AGENT
from zero_core.agents.git_agent import DEFAULT_GIT_AGENT
from zero_core.agents.project_builder import DEFAULT_PROJECT_BUILDER
from zero_core.memory.project_knowledge import DEFAULT_PROJECT_KNOWLEDGE
from zero_core.tools.base import BaseTool, tool


class SearchProjectInput(BaseModel):
    query: str = Field(description="Search keywords or project ID (e.g. 'architecture', 'zero', 'trading_bot')")


class GitInspectInput(BaseModel):
    include_commits: bool = Field(default=True, description="Whether to include recent commit logs in inspection")


class ScaffoldProjectInput(BaseModel):
    project_name: str = Field(description="Name of the new software project to scaffold")
    target_dir: str = Field(description="Destination directory path on disk")
    idea_summary: str = Field(default="", description="Detailed description of the product idea and requirements")


class RunProjectTestsInput(BaseModel):
    project_dir: str = Field(description="Path to the project directory containing tests")


@tool(
    name="project_search_knowledge",
    description="Searches indexed project architecture, blueprints, stack details, and repositories.",
    args_model=SearchProjectInput,
    risk_level="read_only",
)
def project_search_knowledge_tool(query: str) -> str:
    return DEFAULT_PROJECT_KNOWLEDGE.answer_status_query(query)


@tool(
    name="project_git_status",
    description="Inspects active Git branch, uncommitted files, modified tracks, and recent commits.",
    args_model=GitInspectInput,
    risk_level="read_only",
)
def project_git_status_tool(include_commits: bool = True) -> str:
    report = DEFAULT_GIT_AGENT.inspect_status()
    return report.summary()


@tool(
    name="project_scaffold",
    description="Autonomously scaffolds a complete new project directory layout, specification docs (SRS, Architecture, Roadmap), and starter code.",
    args_model=ScaffoldProjectInput,
    risk_level="safe_write",
)
def project_scaffold_tool(
    project_name: str,
    target_dir: str,
    idea_summary: str = "",
) -> Dict[str, Any]:
    dest = Path(target_dir).resolve()
    return DEFAULT_PROJECT_BUILDER.scaffold_project(
        project_name=project_name,
        target_dir=dest,
        idea=idea_summary,
    )


@tool(
    name="project_run_tests",
    description="Executes automated pytest test suites on any target project and returns structured execution metrics.",
    args_model=RunProjectTestsInput,
    risk_level="read_only",
)
def project_run_tests_tool(project_dir: str) -> Dict[str, Any]:
    target = Path(project_dir).resolve()
    res = DEFAULT_CODING_AGENT.run_project_tests(target)
    return res.to_dict()


PROJECT_TOOLS: List[BaseTool] = [
    project_search_knowledge_tool,
    project_git_status_tool,
    project_scaffold_tool,
    project_run_tests_tool,
]
