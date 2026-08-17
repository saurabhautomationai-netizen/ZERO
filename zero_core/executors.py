"""Turns a selected AgentSpec into an actual answer.

This closes the gap ARCHITECTURE.md flagged as "Agent execution — the
Orchestrator currently only decides, it doesn't invoke." It closes it
honestly, not by faking it:

- ZERO-native agents backed by a real read adapter (Trading, Finance) get
  executed for real — deterministic Python, no LLM involved, same as
  calling any other function.
- ZERO-native agents with no adapter yet (Trading Coach, Email, Calendar)
  return a clear "not implemented" string instead of pretending.
- Agency-agents specialists are NEVER executed here. This module has no
  LLM client in it. "Executing" a persona means handing its system-prompt
  text to an actual model call, which belongs in the interface layer
  (Telegram/Web, Phase 2) — not in routing/adapter code. `execute()`
  returns `needs_llm=True` plus the raw persona text for that layer to use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from zero_core.agent_registry import AgencyAgentsAdapter, AgentSpec
from zero_core.agents.automation_agent import DEFAULT_AUTOMATION_AGENT
from zero_core.agents.briefing_agent import DEFAULT_BRIEFING_AGENT
from zero_core.agents.calendar_agent import DEFAULT_CALENDAR_AGENT
from zero_core.agents.coding_agent import DEFAULT_CODING_AGENT
from zero_core.agents.deployment_agent import DEFAULT_DEPLOYMENT_AGENT
from zero_core.agents.email_agent import DEFAULT_EMAIL_AGENT
from zero_core.agents.git_agent import DEFAULT_GIT_AGENT
from zero_core.agents.learning_agent import DEFAULT_LEARNING_AGENT
from zero_core.agents.news_agent import DEFAULT_NEWS_AGENT
from zero_core.agents.project_builder import DEFAULT_PROJECT_BUILDER
from zero_core.agents.research_agent import DEFAULT_RESEARCH_AGENT
from zero_core.agents.trading_coach import DEFAULT_TRADING_COACH
from zero_core.finance_status import FinanceDBUnavailable, FinanceStatusAdapter
from zero_core.memory.project_knowledge import DEFAULT_PROJECT_KNOWLEDGE
from zero_core.trading_live_reader import DEFAULT_MT5_READER
from zero_core.trading_status import TradingStatusAdapter


@dataclass
class ExecutionResult:
    spec: Optional[AgentSpec]
    answer: Optional[str]           # set when ZERO could produce a real answer itself
    needs_llm: bool                  # True => caller must run an LLM call with `persona`
    persona: Optional[str] = None     # full persona markdown, only set when needs_llm


def _execute_finance_agent(task: str) -> str:
    try:
        recent = FinanceStatusAdapter().get_recent_transactions(limit=5)
    except FinanceDBUnavailable as exc:
        return f"Finance Agent not configured yet: {exc}"
    if not recent:
        return "Finance Agent: connected, but no transactions found."
    lines = [f"Last {len(recent)} transaction(s):"]
    for t in recent:
        lines.append(
            f"  {t.transaction_date} | {t.category or 'Uncategorized'} | "
            f"{t.vendor or '-'} | {t.amount} {t.currency or ''}"
        )
    return "\n".join(lines)


def _execute_trading_agent(task: str) -> str:
    signal_status = TradingStatusAdapter().get_status().summary()
    t_lower = task.lower()
    if any(w in t_lower for w in ("position", "account", "equity", "balance", "margin", "p&l", "pnl", "live")):
        acc_status = DEFAULT_MT5_READER.get_account_status().summary()
        return f"{signal_status}\n\n{acc_status}"
    return signal_status


def _execute_trading_coach(task: str) -> str:
    return DEFAULT_TRADING_COACH.answer_question(task)


def _execute_email_agent(task: str) -> str:
    return DEFAULT_EMAIL_AGENT.summarize_inbox()


def _execute_calendar_agent(task: str) -> str:
    return DEFAULT_CALENDAR_AGENT.summarize_schedule()


def _execute_research_agent(task: str) -> str:
    report = DEFAULT_RESEARCH_AGENT.synthesize_research(topic=task)
    return report.to_markdown()


def _execute_project_builder(task: str) -> str:
    t_lower = task.lower()
    if any(k in t_lower for k in ("status of", "architecture of", "project status", "search project", "show me project", "what changed")):
        for p in DEFAULT_PROJECT_KNOWLEDGE._projects.values():
            if p.project_id in t_lower or p.name.lower() in t_lower or p.project_id.replace("_", " ") in t_lower:
                return p.summary()
        return DEFAULT_PROJECT_KNOWLEDGE.answer_status_query(task)
    blueprint = DEFAULT_PROJECT_BUILDER.build_blueprint(project_name=task, idea=task)
    return blueprint.to_markdown()


def _execute_coding_agent(task: str) -> str:
    return DEFAULT_CODING_AGENT.explain_code(summary_topic=task)


def _execute_git_agent(task: str) -> str:
    return DEFAULT_GIT_AGENT.inspect_status().summary()


def _execute_learning_agent(task: str) -> str:
    return DEFAULT_LEARNING_AGENT.generate_learning_plan()


def _execute_automation_agent(task: str) -> str:
    return DEFAULT_AUTOMATION_AGENT.summarize_automations()


def _execute_briefing_agent(task: str) -> str:
    report = DEFAULT_BRIEFING_AGENT.generate_morning_briefing()
    return report.to_markdown()


def _execute_deployment_agent(task: str) -> str:
    report = DEFAULT_DEPLOYMENT_AGENT.run_health_check()
    return report.to_markdown()


def _execute_news_agent(task: str) -> str:
    return DEFAULT_NEWS_AGENT.get_daily_digest()


def _not_implemented(name: str) -> Callable[[str], str]:
    def _inner(task: str) -> str:
        return f"{name} is a planned ZERO-native agent, not implemented yet (see native_agents.py)."
    return _inner


# Every slug in native_agents.ALL_NATIVE_AGENTS must appear here — enforced
# by test_all_native_agents_have_an_executor, same "single source of truth,
# checked" pattern the Agency-agents review called out as worth copying.
NATIVE_EXECUTORS: dict[str, Callable[[str], str]] = {
    "native/finance-agent": _execute_finance_agent,
    "native/trading-agent": _execute_trading_agent,
    "native/trading-coach": _execute_trading_coach,
    "native/email-agent": _execute_email_agent,
    "native/calendar-agent": _execute_calendar_agent,
    "native/research-agent": _execute_research_agent,
    "native/project-builder": _execute_project_builder,
    "native/coding-agent": _execute_coding_agent,
    "native/git-agent": _execute_git_agent,
    "native/learning-agent": _execute_learning_agent,
    "native/automation-agent": _execute_automation_agent,
    "native/briefing-agent": _execute_briefing_agent,
    "native/deployment-agent": _execute_deployment_agent,
    "native/news-agent": _execute_news_agent,
}


def execute(
    spec: AgentSpec,
    task: str,
    agency_adapter: Optional[AgencyAgentsAdapter] = None,
) -> ExecutionResult:
    if spec.source == "native":
        fn = NATIVE_EXECUTORS.get(spec.slug)
        if fn is None:
            return ExecutionResult(
                spec=spec,
                answer=f"No executor registered for {spec.slug} — this is a bug, "
                       f"file it against zero_core/executors.py.",
                needs_llm=False,
            )
        return ExecutionResult(spec=spec, answer=fn(task), needs_llm=False)

    # Agency specialist: hand off the persona, don't fake executing it.
    persona_text = None
    if agency_adapter is not None:
        try:
            persona_text = agency_adapter.load_persona(spec)
        except (ValueError, OSError):
            persona_text = None
    return ExecutionResult(spec=spec, answer=None, needs_llm=True, persona=persona_text)
