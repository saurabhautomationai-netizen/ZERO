from __future__ import annotations

from zero_core.memory.project_knowledge import (
    DEFAULT_PROJECT_KNOWLEDGE,
    ProjectKnowledgeStore,
    ProjectProfile,
)


def test_project_knowledge_query_defaults():
    store = ProjectKnowledgeStore()

    # Query Trading Bot
    trading = store.get_project("trading_bot")
    assert trading is not None
    assert "Live automated trading bot" in trading.purpose
    assert "MetaTrader5" in trading.tech_stack

    # Query Finance Tracker
    finance = store.get_project("finance_tracker")
    assert finance is not None
    assert "118-node n8n workflow" in finance.purpose

    # Query ZERO
    zero = store.get_project("zero")
    assert zero is not None
    assert "Personal AI Operating System" in zero.name


def test_project_knowledge_search_and_status_summary():
    store = ProjectKnowledgeStore()

    results = store.search_projects("n8n")
    assert len(results) >= 1
    assert results[0].project_id == "finance_tracker"

    status_ans = store.answer_status_query("Trading Bot")
    assert "Trading Bot (MT5 Live System)" in status_ans
    assert "Architecture Overview" in status_ans
    assert "Roadmap" in status_ans


def test_project_knowledge_custom_project_addition():
    store = ProjectKnowledgeStore()
    store.add_project(
        ProjectProfile(
            project_id="hr_bot",
            name="HR Recruitment Assistant",
            purpose="Resume screening and interview scheduling pipeline.",
            tech_stack=["Python", "FastAPI", "OpenAI"],
            current_status="In Conception",
            architecture_overview="Modular ATS webhook listener with candidate scoring engine.",
        )
    )

    hr = store.get_project("hr_bot")
    assert hr is not None
    assert hr.name == "HR Recruitment Assistant"
