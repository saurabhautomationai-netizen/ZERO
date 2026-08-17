"""ZERO-native agents.

Per the architecture decision in ARCHITECTURE.md: native agent *personas*
live here, inside the ZERO repo — not as a "zero" division bolted onto the
Agency-agents clone. Reasons:

  1. Agency-agents is a git clone tracking an external upstream
     (`origin/main`). Mixing your private, personal-data-bound agents into
     that tree risks a `git pull` conflict and, worse, an accidental push
     of personal context to a public fork.
  2. ZERO must "remain the owner of the architecture" (your words) —
     native agents need access to Memory/RAG, your DB credentials, and
     approval flows that Agency-agents personas were never designed to
     carry (they're stateless prompt files with no concept of your data).

Each entry below is a *stub*: enough structure for the Agent Registry to
route to it and for you to see exactly what's implemented vs. planned. None
of them re-implement Trading bot or Personal Finance Tracker — see the
`integration_note` on each for how it's meant to call into that existing
project instead.
"""

from __future__ import annotations

from zero_core.agent_registry import AgentSpec
from zero_core import config


def _native(name, slug, division, description, keywords, integration_note):
    """Small factory so each stub below stays a readable one-liner block."""
    return AgentSpec(
        name=name,
        slug=slug,
        source="native",
        division=division,
        description=f"{description}\n\nIntegration: {integration_note}",
        keywords=tuple(keywords),
    )


FINANCE_AGENT = _native(
    name="Finance Agent",
    slug="native/finance-agent",
    division="zero-native",
    description="Owns your transaction database, subscriptions, budgets, and financial history.",
    keywords=["budget", "expense", "subscription", "spending", "transaction", "finance tracker"],
    integration_note=(
        "CORRECTED after inspecting the live n8n workflow (initial assumption of "
        "'prompt-driven .txt files' was wrong): 'Zero Finance Tracker' is a 118-node n8n "
        "workflow (Telegram/WhatsApp intake across text/voice/image/PDF/XLSX, budget alerts, "
        "anomaly detection, subscriptions, loans, credit cards, monthly reports, forecasting, "
        "and its own Finance Chat Agent). Transactions land in a real Postgres table "
        "(public.transactions / public.users) — everything else (sheets, reports, alerts) "
        "stays in n8n; ZERO does not duplicate it. "
        "Phase 1.5b DELIVERED: zero_core.finance_status.FinanceStatusAdapter reads "
        "transactions/category totals read-only, via a DEDICATED read-only DB role "
        "(FINANCE_DB_URL — not yet configured; see finance_status.py docstring for the "
        "CREATE ROLE SQL to run yourself). "
        "May call Agency-agents Financial Analyst / FP&A Analyst / Tax Strategist personas for "
        "deep-dive analysis it doesn't own itself (see agent_registry.AgentRegistry.resolve)."
    ),
)

TRADING_AGENT = _native(
    name="Trading Agent",
    slug="native/trading-agent",
    division="zero-native",
    description="Interfaces with your live trading system (MT5 bridge, execution/risk engines).",
    keywords=["trade", "trading", "mt5", "position", "backtest", "strategy signal"],
    integration_note=(
        f"Wraps the existing 'Trading bot' project at {config.SIBLING_PROJECTS['trading_bot']} — "
        "a mature, standalone, LIVE trading system (mt5_bridge.py, risk_validator.py, "
        "paper_live_buy/sell.py). Do NOT reimplement any of this. "
        "Phase 1.5 DELIVERED: zero_core.trading_status.TradingStatusAdapter reads "
        "trade_state.json / trade_state_buy.json / trade_state_sell.json / "
        "last_signal_time.txt — read-only, no import of mt5_bridge/mt5_executor (enforced by "
        "a test). Answers 'what's the bot's last signal / is a buy trade currently active'. "
        "IMPORTANT: these files carry signal-detection state (last candle, active_buy_trade "
        "flag, pending SMC pattern memory), NOT a position ledger — no entry price, lot size, "
        "or live P&L in them. Real-time position/P&L would need a live MT5 query, which is a "
        "separate, bigger, still-undecided scope (execute-adjacent even if read-only)."
    ),
)

TRADING_COACH = _native(
    name="Trading Coach",
    slug="native/trading-coach",
    division="zero-native",
    description="Your trading-specific RAG — historical context over your own trades, not generic advice.",
    keywords=["trading coach", "why did i lose", "trade review", "setup history"],
    integration_note=(
        "Depends on Memory/RAG (pgvector) being built first — see zero_core/memory. Ingests "
        "bot logs, trade data, and MT5 reports from the Trading bot project into embeddings, "
        "distinct from the Trading Agent above (that one *acts*; this one *explains*, using your "
        "actual history rather than Agency-agents' generic Investment Researcher persona). "
        "NOT STARTED — Phase 3+."
    ),
)

EMAIL_AGENT = _native(
    name="Email Agent",
    slug="native/email-agent",
    division="zero-native",
    description="Gmail integration — triage, drafting, summarization.",
    keywords=["email", "gmail", "inbox"],
    integration_note="DELIVERED (M12): zero_core.agents.email_agent.EmailAgent.",
)

CALENDAR_AGENT = _native(
    name="Calendar Agent",
    slug="native/calendar-agent",
    division="zero-native",
    description="Calendar read/write, scheduling, conflict detection.",
    keywords=["calendar", "schedule", "meeting", "appointment"],
    integration_note="DELIVERED (M13): zero_core.agents.calendar_agent.CalendarAgent.",
)

RESEARCH_AGENT = _native(
    name="Research Agent",
    slug="native/research-agent",
    division="zero-native",
    description="Autonomous multi-source technical research, literature synthesis, and citation tracking.",
    keywords=["research", "literature", "compare", "citation", "technical report", "synthesis"],
    integration_note="DELIVERED (M14): zero_core.agents.research_agent.ResearchAgent.",
)

PROJECT_BUILDER = _native(
    name="Project Builder",
    slug="native/project-builder",
    division="zero-native",
    description="Orchestrates software inception: Idea -> SRS -> Architecture -> ADRs -> Folder Structure -> Roadmap.",
    keywords=[
        "project builder", "build project", "create project", "srs",
        "architecture plan", "scaffold", "blueprint", "project blueprint",
        "design and build", "build a complete", "build system", "system architecture"
    ],
    integration_note="DELIVERED (M15): zero_core.agents.project_builder.ProjectBuilderAgent.",
)

CODING_AGENT = _native(
    name="Coding Agent",
    slug="native/coding-agent",
    division="zero-native",
    description="Static AST code analysis, refactoring unified diff generation, and clean architecture reviews.",
    keywords=["coding", "code analysis", "refactor", "ast", "diff", "code review"],
    integration_note="DELIVERED (M16): zero_core.agents.coding_agent.CodingAgent.",
)

GIT_AGENT = _native(
    name="Git Agent",
    slug="native/git-agent",
    division="zero-native",
    description="Git working tree status inspection, conventional commit generation, and safety guardrails.",
    keywords=["git", "commit", "working tree", "branch", "git status"],
    integration_note="DELIVERED (M16): zero_core.agents.git_agent.GitAgent.",
)

LEARNING_AGENT = _native(
    name="Learning Agent",
    slug="native/learning-agent",
    division="zero-native",
    description="Personalized mastery tracking, weak-area diagnostic revision quizzes, and study roadmaps.",
    keywords=["learning", "mastery", "quiz", "revision", "study plan", "curriculum", "learning plan", "mastery plan"],
    integration_note="DELIVERED (M18): zero_core.agents.learning_agent.LearningAgent.",
)

AUTOMATION_AGENT = _native(
    name="Automation Agent",
    slug="native/automation-agent",
    division="zero-native",
    description="Interfaces with n8n workflows and webhooks to trigger tasks and monitor automation health.",
    keywords=["automation", "n8n", "webhook", "trigger workflow", "automation status"],
    integration_note="DELIVERED: zero_core.agents.automation_agent.AutomationAgent.",
)

BRIEFING_AGENT = _native(
    name="Briefing Agent",
    slug="native/briefing-agent",
    division="zero-native",
    description="Generates unified morning and evening executive briefings across finance, trading, email, and calendar.",
    keywords=["briefing", "daily brief", "morning brief", "evening brief", "digest", "summary for today", "brief", "brife", "morning"],
    integration_note="DELIVERED: zero_core.agents.briefing_agent.BriefingAgent.",
)

DEPLOYMENT_AGENT = _native(
    name="Deployment Agent",
    slug="native/deployment-agent",
    division="zero-native",
    description="System-wide diagnostic inspections, database connectivity verification, and subsystem readiness reports.",
    keywords=["deployment", "health check", "subsystem health", "diagnostics", "readiness", "system status"],
    integration_note="DELIVERED: zero_core.agents.deployment_agent.DeploymentAgent.",
)

NEWS_AGENT = _native(
    name="News Agent",
    slug="native/news-agent",
    division="zero-native",
    description="Real-time multi-category news aggregator and digest synthesizer powered by The Hindu RSS.",
    keywords=["news", "the hindu", "daily news", "news update", "news summary", "headlines", "current affairs", "top news"],
    integration_note="DELIVERED: zero_core.agents.news_agent.NewsAgent.",
)


ALL_NATIVE_AGENTS: list[AgentSpec] = [
    FINANCE_AGENT,
    TRADING_AGENT,
    TRADING_COACH,
    EMAIL_AGENT,
    CALENDAR_AGENT,
    RESEARCH_AGENT,
    PROJECT_BUILDER,
    CODING_AGENT,
    GIT_AGENT,
    LEARNING_AGENT,
    AUTOMATION_AGENT,
    BRIEFING_AGENT,
    DEPLOYMENT_AGENT,
    NEWS_AGENT,
]

