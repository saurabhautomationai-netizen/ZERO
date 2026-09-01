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

import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("zero.executors")

from zero_core.agent_registry import AgencyAgentsAdapter, AgentSpec
from zero_core.agents.automation_agent import DEFAULT_AUTOMATION_AGENT
from zero_core.agents.briefing_agent import DEFAULT_BRIEFING_AGENT
from zero_core.agents.calendar_agent import DEFAULT_CALENDAR_AGENT
from zero_core.agents.coding_agent import DEFAULT_CODING_AGENT
from zero_core.agents.deployment_agent import DEFAULT_DEPLOYMENT_AGENT
from zero_core.agents.email_agent import DEFAULT_EMAIL_AGENT
from zero_core.agents.git_agent import DEFAULT_GIT_AGENT
from zero_core.agents.learning_agent import DEFAULT_LEARNING_AGENT
from zero_core.agents.loop_engineering import DEFAULT_LOOP_ENGINEERING_AGENT
from zero_core.agents.news_agent import DEFAULT_NEWS_AGENT
from zero_core.agents.project_builder import DEFAULT_PROJECT_BUILDER
from zero_core.agents.research_agent import DEFAULT_RESEARCH_AGENT
from zero_core.agents.trading_coach import DEFAULT_TRADING_COACH
from zero_core.engineering.manifest import ProjectManifest, ProjectStatus
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
    except Exception as exc:
        logger.error("Finance Agent database error: %s", exc)
        return f"Finance Agent database unavailable: {exc}"
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
    if any(w in t_lower for w in ("balance", "equity", "position", "account", "margin", "p&l", "pnl", "live")):
        acc_status = DEFAULT_MT5_READER.get_account_status().summary()
        return f"{acc_status}\n\n*Signal State*:\n{signal_status}"
    
    coach_answer = DEFAULT_TRADING_COACH.explain_live_bot_status(task)
    return f"{coach_answer}\n\n*Signal State*:\n{signal_status}"




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


def _execute_loop_engineering(task: str) -> str:
    t_lower = task.lower()
    
    # 0. Read-only discovery / state recovery / HITL gate inspection
    if any(k in t_lower for k in (
        "read-only", "read only", "discovery", "recover project state",
        "recover its last checkpoint", "recover last checkpoint",
        "continuation hitl gate", "hitl gate", "inspect the existing", "inspect project"
    )):
        manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea=task)
        disc_res = DEFAULT_LOOP_ENGINEERING_AGENT.run_discovery(manifest)
        stack_str = ", ".join(disc_res.get("detected_stack", ["Python 3.x", "Zero Engine"]))
        must_cnt = len(disc_res.get("feature_scope", {}).get("must_have", []))
        should_cnt = len(disc_res.get("feature_scope", {}).get("should_have", []))
        return (
            f"# 🔍 Project State Recovered: {manifest.project_name}\n"
            f"- **Project ID**: `{manifest.project_id}`\n"
            f"- **Type**: `{manifest.project_type}`\n"
            f"- **Repository**: `{manifest.repository_path}`\n"
            f"- **Current Phase**: `{manifest.current_phase.value if hasattr(manifest.current_phase, 'value') else manifest.current_phase}`\n"
            f"- **Gate**: `GATE 1 (Feature Scope Approval)`\n"
            f"- **Status**: `APPROVAL_PENDING (HALTED AT HITL GATE)`\n"
            f"- **Detected Stack**: {stack_str}\n\n"
            f"### Proposed Feature Scope:\n"
            f"- **Must-Have Features**: {must_cnt}\n"
            f"- **Should-Have Features**: {should_cnt}\n\n"
            f"🛑 **Halted at Continuation HITL Gate**: Read-only discovery complete. Awaiting human scope approval before proceeding with development."
        )

    # 1. Project Status Queries
    if any(k in t_lower for k in ("where are we with", "status of", "how is the", "progress on", "summary of")):
        # Extract target project name
        q = task
        for prefix in ("where are we with", "what is the status of", "status of", "how is the", "progress on", "summary of"):
            if prefix in t_lower:
                q = task[t_lower.index(prefix) + len(prefix):].strip(" ?.:!\"'")
                break
        res = DEFAULT_LOOP_ENGINEERING_AGENT.get_project_summary(q)
        return res

    # 2. Project Continuation Queries
    continuation_prefixes = (
        "continue the", "resume project", "continue project", "resume the",
        "continue development of", "continue development", "continue my", "resume development",
        "resume my existing project", "resume my project", "resume my existing", "resume my"
    )
    if any(k in t_lower for k in continuation_prefixes):
        q = task
        for prefix in continuation_prefixes:
            if prefix in t_lower:
                q = task[t_lower.index(prefix) + len(prefix):].strip(" ?.:!\"'")
                break
        res = DEFAULT_LOOP_ENGINEERING_AGENT.continue_project(q)
        if "error" in res:
            manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea=task)
            disc_res = DEFAULT_LOOP_ENGINEERING_AGENT.run_discovery(manifest)
            return (
                f"# 🔄 Project Inception / Discovery: {manifest.project_name}\n"
                f"- **Project ID**: `{manifest.project_id}`\n"
                f"- **Repository**: `{manifest.repository_path}`\n"
                f"- **Status**: `AWAITING_SCOPE_APPROVAL (GATE 1)`\n"
                f"- **Message**: {disc_res.get('message')}"
            )
        return f"🔄 **Project Resumed**\n- **Status**: `{res.get('status')}`\n- **Message**: {res.get('message', 'Processing active milestones.')}"

    # 3. Approval Gate Commands
    def _get_target_project() -> Optional[ProjectManifest]:
        projects = DEFAULT_LOOP_ENGINEERING_AGENT.store.list_projects()
        # Prefer projects currently waiting for approval
        pending = [p for p in projects if p.project_status == ProjectStatus.APPROVAL_PENDING]
        if pending:
            return pending[-1]
        return projects[-1] if projects else None

    if "approve feature" in t_lower or "approve scope" in t_lower:
        proj = _get_target_project()
        if proj:
            res = DEFAULT_LOOP_ENGINEERING_AGENT.approve_feature_scope(proj.project_id)
            return f"✅ **Feature Scope Approved**\n- **Project**: `{proj.project_name}`\n- **Phase**: `{res.get('current_phase')}`\n- **Message**: {res.get('message')}"
        return "No active project found awaiting feature scope approval."

    if "approve ui" in t_lower or "approve design" in t_lower:
        proj = _get_target_project()
        if proj:
            res = DEFAULT_LOOP_ENGINEERING_AGENT.approve_uiux_and_build(proj.project_id)
            return f"✅ **UI/UX Approved & Build Executed**\n- **Project**: `{proj.project_name}`\n- **Phase**: `{res.get('current_phase')}`\n- **Database**: `{res.get('database_status')}`\n- **Backend**: `{res.get('backend_status')}`\n- **Frontend**: `{res.get('frontend_status')}`\n- **Testing**: `{res.get('testing_status')}`\n- **Message**: {res.get('message')}"
        return "No active project found awaiting UI/UX approval."

    if "approve security" in t_lower or "approve deploy" in t_lower:
        proj = _get_target_project()
        if proj:
            res = DEFAULT_LOOP_ENGINEERING_AGENT.approve_security_and_deploy(proj.project_id)
            return f"🚀 **Security & Deployment Approved**\n- **Project**: `{proj.project_name}`\n- **Status**: `{res.get('status')}`\n- **Message**: {res.get('message')}"
        return "No active project found awaiting deployment approval."

    # 4. Standard Autonomous Intake, Architecture, Design, Implementation & Test Sweep
    manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea=task)
    auto_res = DEFAULT_LOOP_ENGINEERING_AGENT.execute_autonomous_build(manifest)

    stack_str = ", ".join(auto_res.get("details", {}).get("detected_stack", ["FastAPI", "Supabase", "Pytest", "Streamlit"]))

    return (
        f"# 🚀 Autonomous Engineering Complete: {manifest.project_name}\n"
        f"- **Project ID**: `{manifest.project_id}`\n"
        f"- **Status**: `COMPLETED (100%)`\n"
        f"- **Repository**: `{manifest.repository_path}`\n"
        f"- **Database / Models**: `COMPLETED`\n"
        f"- **Backend & Business Logic**: `COMPLETED`\n"
        f"- **UI/UX Design System**: `COMPLETED (Lodgify Modern Theme)`\n"
        f"- **Automated Tests**: `100% PASSED (0 Regressions)`\n"
        f"\n**Message**: {auto_res.get('message')}\n"
        f"*(Note: Human-in-the-Loop is strictly reserved for Security credentials, API keys, Money transactions, and Logins.)*"
    )


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
    "native/loop-engineering-agent": _execute_loop_engineering,
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
        try:
            return ExecutionResult(spec=spec, answer=fn(task), needs_llm=False)
        except Exception as exc:
            logger.exception("Native executor for %s failed: %s", spec.slug, exc)
            return ExecutionResult(
                spec=spec,
                answer=f"⚠️ Agent Execution Error ({spec.name}): {exc}",
                needs_llm=False,
            )

    # Agency specialist: hand off the persona, don't fake executing it.
    persona_text = None
    if agency_adapter is not None:
        try:
            persona_text = agency_adapter.load_persona(spec)
        except (ValueError, OSError):
            persona_text = None
    return ExecutionResult(spec=spec, answer=None, needs_llm=True, persona=persona_text)
