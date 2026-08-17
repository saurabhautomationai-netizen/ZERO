"""Unit tests for the News Agent in ZERO."""

import pytest
from zero_core.agents.news_agent import NewsAgent, THE_HINDU_FEEDS
from zero_core.executors import NATIVE_EXECUTORS, execute
from zero_core.native_agents import NEWS_AGENT


def test_news_agent_feeds_structure():
    agent = NewsAgent()
    assert "Business & Markets" in agent.feeds
    assert "National Politics" in agent.feeds
    assert "Geopolitics" in agent.feeds
    assert "Science & Tech" in agent.feeds
    assert "Sports" in agent.feeds


def test_news_agent_digest_formatting(monkeypatch):
    agent = NewsAgent(feeds={"Business & Markets": "https://example.com/rss"})

    def mock_fetch(url, limit=2):
        return ["Stock markets surge 500 points", "RBI holds repo rate"]

    monkeypatch.setattr(agent, "fetch_category_headlines", mock_fetch)
    digest = agent.get_daily_digest()

    assert "The Hindu" in digest
    assert "Business & Markets" in digest
    assert "Stock markets surge 500 points" in digest
    assert "RBI holds repo rate" in digest


def test_news_agent_registered_in_executors():
    assert NEWS_AGENT.slug in NATIVE_EXECUTORS
    res = execute(NEWS_AGENT, "the hindu news update")
    assert res.spec == NEWS_AGENT
    assert res.needs_llm is False
    assert "The Hindu" in res.answer
