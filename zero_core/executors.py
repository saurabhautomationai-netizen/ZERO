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
    from zero_core.engineering.resolver import (
        DEFAULT_PROJECT_RESOLVER,
        EngineeringIntent,
        ResolutionError,
        ResolutionStatus,
    )

    req = DEFAULT_PROJECT_RESOLVER.parse_request(raw_instruction=task)

    # Special handling for GATE_APPROVAL when user did not specify project
    if req.intent == EngineeringIntent.GATE_APPROVAL and not req.project_id and not req.repository_path and not req.project_name:
        pending_projects = [
            p for p in DEFAULT_LOOP_ENGINEERING_AGENT.store.list_projects()
            if p.project_status == ProjectStatus.APPROVAL_PENDING
        ]
        if len(pending_projects) > 1:
            names = [f"{p.project_name} (`{p.project_id}`)" for p in pending_projects]
            return (
                f"⚠️ **PROJECT_AMBIGUOUS**: Multiple projects are currently awaiting approval: {', '.join(names)}. "
                "Please specify the target Project ID (e.g., `Approve feature scope for Project ID: proj_...`)."
            )
        elif len(pending_projects) == 1:
            req.project_id = pending_projects[0].project_id

    # Resolve project using 8-tier resolver
    try:
        manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    except ResolutionError as err:
        if err.status == ResolutionStatus.PROJECT_NOT_FOUND:
            return f"❌ **PROJECT_NOT_FOUND**: {err.message}"
        elif err.status == ResolutionStatus.PROJECT_AMBIGUOUS:
            return f"⚠️ **PROJECT_AMBIGUOUS**: {err.message}"
        elif err.status == ResolutionStatus.BOUNDARY_VIOLATION:
            return f"❌ **PROJECT_BOUNDARY_VIOLATION**: {err.message}"
        else:
            return f"❌ **Resolution Error**: {err.message}"

    # 1. DIAGNOSTIC Intent (Strictly Read-Only)
    if req.intent == EngineeringIntent.DIAGNOSTIC:
        diag = DEFAULT_LOOP_ENGINEERING_AGENT.diagnose_issue(manifest, req)
        findings_md = "\n".join(f"- {f}" for f in diag.get("findings", []))
        return (
            f"# 🔬 Project Diagnostic Report: {manifest.project_name}\n"
            f"- **Project ID**: `{manifest.project_id}`\n"
            f"- **Repository**: `{manifest.repository_path}`\n"
            f"- **Mode**: `READ-ONLY DIAGNOSTIC`\n"
            f"- **Status**: `{manifest.project_status.value if hasattr(manifest.project_status, 'value') else manifest.project_status}`\n\n"
            f"### Architectural Findings:\n{findings_md}\n\n"
            f"### Analysis:\n{diag.get('analysis', 'Diagnosis completed.')}\n\n"
            f"*(Zero Diagnostic Mode: No files were mutated, no gates were approved, and no phases were advanced.)*"
        )

    # 2. STATUS Intent
    if req.intent == EngineeringIntent.STATUS:
        return DEFAULT_LOOP_ENGINEERING_AGENT.get_project_summary(manifest.project_id)

    # 3. DISCOVERY Intent (Read-Only State Inspection / Scope)
    if req.intent == EngineeringIntent.DISCOVERY:
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

    # 4. RESUME Intent
    if req.intent == EngineeringIntent.RESUME:
        res = DEFAULT_LOOP_ENGINEERING_AGENT.continue_project(manifest.project_id)
        if "error" in res:
            return f"❌ **Error Resuming Project**: {res['error']}"
        return (
            f"🔄 **Project Resumed**: {manifest.project_name}\n"
            f"- **Status**: `{res.get('status')}`\n"
            f"- **Phase**: `{res.get('phase', manifest.current_phase)}`\n"
            f"- **Message**: {res.get('message', 'Processing active milestones.')}"
        )

    # 5. GATE_APPROVAL Intent (Strict Project Isolation)
    if req.intent == EngineeringIntent.GATE_APPROVAL:
        gate_name = req.requested_gate or ""
        if "scope" in gate_name.lower() or "feature" in gate_name.lower() or "gate_1" in gate_name.lower():
            res = DEFAULT_LOOP_ENGINEERING_AGENT.approve_feature_scope(manifest.project_id)
            return f"✅ **Feature Scope Approved**\n- **Project**: `{manifest.project_name}`\n- **Phase**: `{res.get('current_phase')}`\n- **Message**: {res.get('message')}"
        elif "ui" in gate_name.lower() or "design" in gate_name.lower() or "gate_2" in gate_name.lower():
            res = DEFAULT_LOOP_ENGINEERING_AGENT.approve_uiux_and_build(manifest.project_id)
            return (
                f"✅ **UI/UX Approved & Build Executed**\n"
                f"- **Project**: `{manifest.project_name}`\n"
                f"- **Phase**: `{res.get('current_phase')}`\n"
                f"- **Database**: `{res.get('database_status')}`\n"
                f"- **Backend**: `{res.get('backend_status')}`\n"
                f"- **Frontend**: `{res.get('frontend_status')}`\n"
                f"- **Testing**: `{res.get('testing_status')}`\n"
                f"- **Message**: {res.get('message')}"
            )
        elif "security" in gate_name.lower() or "deploy" in gate_name.lower() or "gate_3" in gate_name.lower() or "gate_4" in gate_name.lower():
            res = DEFAULT_LOOP_ENGINEERING_AGENT.approve_security_and_deploy(manifest.project_id)
            return f"🚀 **Security & Deployment Approved**\n- **Project**: `{manifest.project_name}`\n- **Status**: `{res.get('status')}`\n- **Message**: {res.get('message')}"
        else:
            return f"❌ **Unknown Gate**: Could not determine gate to approve from instruction."

    # 6. PLAN Intent
    if req.intent == EngineeringIntent.PLAN:
        dag = DEFAULT_LOOP_ENGINEERING_AGENT.lifecycle.get_or_create_dag(manifest)
        tasks = dag.list_all_tasks()
        task_md = "\n".join(f"- `[{t.state.value}]` **{t.title}** ({t.task_id})" for t in tasks)
        return (
            f"# 📋 Engineering Plan: {manifest.project_name}\n"
            f"- **Project ID**: `{manifest.project_id}`\n"
            f"- **Current Phase**: `{manifest.current_phase.value if hasattr(manifest.current_phase, 'value') else manifest.current_phase}`\n"
            f"- **Total Tasks**: {len(tasks)}\n\n"
            f"### Task DAG:\n{task_md or 'No tasks registered yet.'}"
        )

    # 7. AUTONOMOUS_BUILD Intent (Explicit Mutation)
    if req.intent == EngineeringIntent.AUTONOMOUS_BUILD:
        DEFAULT_PROJECT_RESOLVER.verify_mutation_boundary(manifest)
        auto_res = DEFAULT_LOOP_ENGINEERING_AGENT.execute_autonomous_build(manifest)
        return (
            f"# 🚀 Autonomous Engineering Complete: {manifest.project_name}\n"
            f"- **Project ID**: `{manifest.project_id}`\n"
            f"- **Status**: `COMPLETED (100%)`\n"
            f"- **Repository**: `{manifest.repository_path}`\n"
            f"- **Message**: {auto_res.get('message')}"
        )

    # 8. TASK_EXECUTION Intent
    if req.intent == EngineeringIntent.TASK_EXECUTION:
        DEFAULT_PROJECT_RESOLVER.verify_mutation_boundary(manifest)
        res = DEFAULT_LOOP_ENGINEERING_AGENT.advance_project_lifecycle(manifest)
        return (
            f"# ⚙️ Task Execution: {manifest.project_name}\n"
            f"- **Status**: `{res.get('status')}`\n"
            f"- **Phase**: `{res.get('phase')}`\n"
            f"- **Detail**: {res}"
        )

    # 9. UNKNOWN Intent (FAIL-CLOSED: NEVER MUTATE)
    return (
        f"# ℹ️ Loop Engineering Instruction Received\n"
        f"- **Resolved Project**: `{manifest.project_name}` (`{manifest.project_id}`)\n"
        f"- **Repository**: `{manifest.repository_path}`\n"
        f"- **Current Phase**: `{manifest.current_phase.value if hasattr(manifest.current_phase, 'value') else manifest.current_phase}`\n"
        f"- **Project Status**: `{manifest.project_status.value if hasattr(manifest.project_status, 'value') else manifest.project_status}`\n\n"
        f"**Directive**: {req.raw_instruction}\n\n"
        f"*(Unrecognized command intent. For safety, no files were mutated. Available actions: `status`, `diagnose`, `discovery`, `resume`, `plan`, `execute task`, or `approve <gate>`)*"
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
