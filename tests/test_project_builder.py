from __future__ import annotations

from zero_core.agents.project_builder import (
    DEFAULT_PROJECT_BUILDER,
    ProjectBlueprint,
    ProjectBuilderAgent,
)
from zero_core.executors import execute
from zero_core.native_agents import PROJECT_BUILDER


def test_project_builder_lifecycle_pipeline():
    builder = ProjectBuilderAgent()
    blueprint = builder.build_blueprint(
        project_name="AI Sales Followup Agent",
        idea="Autonomous CRM assistant that reviews leads and drafts personalized follow-up emails.",
    )
    md = blueprint.to_markdown()

    assert "AI Sales Followup Agent" in md
    assert "Software Requirements Specification (SRS)" in md
    assert "FR-01" in md
    assert "Core Architecture & Layers" in md
    assert "Architecture Decision Records (ADRs)" in md
    assert "Target Folder Structure" in md
    assert "Implementation Roadmap" in md
    assert "ai_sales_followup_agent_core" in md


def test_project_builder_executor_dispatch():
    res = execute(spec=PROJECT_BUILDER, task="HR Recruitment Screening Bot")
    assert res.spec.slug == "native/project-builder"
    assert res.needs_llm is False
    assert "Architectural Blueprint: HR Recruitment Screening Bot" in res.answer
    assert "Implementation Roadmap" in res.answer
