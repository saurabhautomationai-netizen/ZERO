"""Specialized Domain Agents package for ZERO."""

from zero_core.agents.automation_agent import (
    DEFAULT_AUTOMATION_AGENT,
    AutomationAgent,
    WorkflowTriggerPayload,
)
from zero_core.agents.briefing_agent import (
    DEFAULT_BRIEFING_AGENT,
    BriefingAgent,
    DailyBriefingReport,
)
from zero_core.agents.calendar_agent import (
    DEFAULT_CALENDAR_AGENT,
    CalendarAgent,
    CalendarEvent,
)
from zero_core.agents.coding_agent import (
    DEFAULT_CODING_AGENT,
    CodeAnalysisResult,
    CodingAgent,
)
from zero_core.agents.deployment_agent import (
    DEFAULT_DEPLOYMENT_AGENT,
    DeploymentAgent,
    SubsystemHealth,
    SystemHealthReport,
)
from zero_core.agents.email_agent import (
    DEFAULT_EMAIL_AGENT,
    EmailAgent,
    EmailMessage,
)
from zero_core.agents.git_agent import (
    DEFAULT_GIT_AGENT,
    GitAgent,
    GitStatusSummary,
)
from zero_core.agents.learning_agent import (
    DEFAULT_LEARNING_AGENT,
    LearningAgent,
    LearningTopic,
)
from zero_core.agents.news_agent import (
    DEFAULT_NEWS_AGENT,
    NewsAgent,
)
from zero_core.agents.project_builder import (
    DEFAULT_PROJECT_BUILDER,
    ProjectBlueprint,
    ProjectBuilderAgent,
)
from zero_core.agents.research_agent import (
    DEFAULT_RESEARCH_AGENT,
    ResearchAgent,
    ResearchReport,
    ResearchSource,
)
from zero_core.agents.trading_coach import (
    DEFAULT_TRADING_COACH,
    TradeLogRecord,
    TradingCoachAgent,
)

__all__ = [
    "TradingCoachAgent",
    "TradeLogRecord",
    "DEFAULT_TRADING_COACH",
    "EmailAgent",
    "EmailMessage",
    "DEFAULT_EMAIL_AGENT",
    "CalendarAgent",
    "CalendarEvent",
    "DEFAULT_CALENDAR_AGENT",
    "ResearchAgent",
    "ResearchSource",
    "ResearchReport",
    "DEFAULT_RESEARCH_AGENT",
    "ProjectBuilderAgent",
    "ProjectBlueprint",
    "DEFAULT_PROJECT_BUILDER",
    "CodingAgent",
    "CodeAnalysisResult",
    "DEFAULT_CODING_AGENT",
    "GitAgent",
    "GitStatusSummary",
    "DEFAULT_GIT_AGENT",
    "LearningAgent",
    "LearningTopic",
    "DEFAULT_LEARNING_AGENT",
    "AutomationAgent",
    "WorkflowTriggerPayload",
    "DEFAULT_AUTOMATION_AGENT",
    "BriefingAgent",
    "DailyBriefingReport",
    "DEFAULT_BRIEFING_AGENT",
    "DeploymentAgent",
    "SystemHealthReport",
    "SubsystemHealth",
    "DEFAULT_DEPLOYMENT_AGENT",
]
