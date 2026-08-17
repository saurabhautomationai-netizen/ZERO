from __future__ import annotations

from zero_core.agents.learning_agent import (
    DEFAULT_LEARNING_AGENT,
    LearningAgent,
    LearningTopic,
)
from zero_core.executors import execute
from zero_core.native_agents import LEARNING_AGENT


def test_learning_agent_track_and_plan():
    agent = LearningAgent()
    assert "No topics currently tracked" in agent.generate_learning_plan()

    agent.track_topic(
        topic_id="langgraph_state_machines",
        title="LangGraph Decoupled State Machines",
        category="Architecture",
        score=0.85,
        weak_areas=["Cyclic error recovery graphs"],
    )

    agent.track_topic(
        topic_id="mt5_risk_management",
        title="MT5 Risk Sizing & Execution Models",
        category="Trading",
        score=0.92,
    )

    plan = agent.generate_learning_plan()
    assert "Personal Learning & Mastery Plan" in plan
    assert "LangGraph Decoupled State Machines" in plan
    assert "85% Mastery" in plan
    assert "Cyclic error recovery" in plan


def test_learning_agent_generate_quiz():
    agent = LearningAgent()
    agent.track_topic(
        topic_id="solid_principles",
        title="SOLID Principles",
        category="Software Engineering",
        score=0.75,
    )

    quiz = agent.generate_quiz("solid_principles")
    assert quiz["topic"] == "SOLID Principles"
    assert len(quiz["questions"]) >= 2


def test_learning_agent_executor_dispatch():
    res = execute(spec=LEARNING_AGENT, task="What is my current study plan?")
    assert res.spec.slug == "native/learning-agent"
    assert res.needs_llm is False
    assert "Learning Agent:" in res.answer or "Personal Learning" in res.answer
