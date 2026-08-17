from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import zero_core.executors as ex
from zero_core.agent_registry import AgencyAgentsAdapter, AgentSpec
from zero_core.native_agents import ALL_NATIVE_AGENTS


def test_all_native_agents_have_an_executor():
    """Consistency check, same spirit as Agency-agents' own check-divisions.sh:
    every registered native agent must have a matching executor, so adding a
    new native agent without wiring it up fails loudly, not silently.
    """
    registered_slugs = {a.slug for a in ALL_NATIVE_AGENTS}
    executor_slugs = set(ex.NATIVE_EXECUTORS.keys())
    assert registered_slugs == executor_slugs


def test_finance_agent_reports_not_configured_when_no_db_url(monkeypatch):
    monkeypatch.delenv("FINANCE_DB_URL", raising=False)
    finance_spec = next(a for a in ALL_NATIVE_AGENTS if a.slug == "native/finance-agent")

    result = ex.execute(finance_spec, "what did I spend on food?")

    assert result.needs_llm is False
    assert "not configured yet" in result.answer.lower()
    assert "FINANCE_DB_URL" in result.answer


def test_trading_agent_executor_calls_status_adapter(monkeypatch):
    fake_status = MagicMock()
    fake_status.summary.return_value = "[buy] last_candle=2026-08-04, active_buy_trade=False"
    fake_adapter_cls = MagicMock(return_value=MagicMock(get_status=MagicMock(return_value=fake_status)))
    monkeypatch.setattr(ex, "TradingStatusAdapter", fake_adapter_cls)

    trading_spec = next(a for a in ALL_NATIVE_AGENTS if a.slug == "native/trading-agent")
    result = ex.execute(trading_spec, "what's my current position?")

    assert result.needs_llm is False
    assert "active_buy_trade=False" in result.answer


def test_unimplemented_native_agent_says_so_not_crash():
    custom_spec = AgentSpec(name="Custom Native", slug="native/custom-stub", source="native", division="zero-native")
    result = ex.execute(custom_spec, "do something new")
    assert result.needs_llm is False
    assert "no executor registered" in result.answer.lower()


def test_agency_spec_hands_off_persona_instead_of_faking_an_answer(tmp_path):
    (tmp_path / "engineering").mkdir()
    (tmp_path / "engineering" / "engineering-fake.md").write_text(
        "---\nname: Fake Engineer\ndescription: x\ncolor: blue\n---\nBody text here.",
        encoding="utf-8",
    )
    adapter = AgencyAgentsAdapter(root=tmp_path, divisions=["engineering"], inventory_snapshot=Path("/nonexistent"))
    spec = adapter.get("engineering/engineering-fake")

    result = ex.execute(spec, "review this code", agency_adapter=adapter)

    assert result.needs_llm is True
    assert result.answer is None
    assert "Fake Engineer" in result.persona


def test_agency_spec_without_adapter_is_still_safe():
    spec = AgentSpec(name="X", slug="engineering/x", source="agency", division="engineering")
    result = ex.execute(spec, "task", agency_adapter=None)
    assert result.needs_llm is True
    assert result.persona is None  # no crash, just nothing to hand off
