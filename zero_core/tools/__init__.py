"""Tools and Tool Registry package for ZERO."""

from typing import List

from zero_core.tools.base import BaseTool, ToolResult, tool
from zero_core.tools.definitions.filesystem import (
    BUILTIN_TOOLS as FILESYSTEM_TOOLS,
    list_dir_tool,
    read_file_tool,
    system_status_tool,
)
from zero_core.tools.definitions.finance_tools import (
    FINANCE_TOOLS,
    finance_category_totals_tool,
    finance_recent_transactions_tool,
)
from zero_core.tools.definitions.project_tools import (
    PROJECT_TOOLS,
    project_git_status_tool,
    project_run_tests_tool,
    project_scaffold_tool,
    project_search_knowledge_tool,
)
from zero_core.tools.definitions.trading_tools import (
    TRADING_TOOLS,
    trading_bot_signals_tool,
    trading_coach_query_tool,
    trading_mt5_account_status_tool,
    trading_preflight_check_tool,
)
from zero_core.tools.definitions.workspace_tools import (
    WORKSPACE_TOOLS,
    workspace_calendar_agenda_tool,
    workspace_create_email_draft_tool,
    workspace_schedule_event_tool,
    workspace_send_email_tool,
    workspace_unread_emails_tool,
)
from zero_core.tools.registry import ToolRegistry

ALL_BUILTIN_TOOLS: List[BaseTool] = (
    list(FILESYSTEM_TOOLS)
    + list(FINANCE_TOOLS)
    + list(TRADING_TOOLS)
    + list(WORKSPACE_TOOLS)
    + list(PROJECT_TOOLS)
)


def build_default_tool_registry() -> ToolRegistry:
    """Factory returning a ToolRegistry pre-populated with standard built-in tools."""
    return ToolRegistry(tools=list(ALL_BUILTIN_TOOLS))


# Alias for backward compatibility
get_default_tool_registry = build_default_tool_registry
BUILTIN_TOOLS = ALL_BUILTIN_TOOLS

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "tool",
    "build_default_tool_registry",
    "get_default_tool_registry",
    "ALL_BUILTIN_TOOLS",
    "BUILTIN_TOOLS",
    "FILESYSTEM_TOOLS",
    "FINANCE_TOOLS",
    "TRADING_TOOLS",
    "WORKSPACE_TOOLS",
    "PROJECT_TOOLS",
    "read_file_tool",
    "list_dir_tool",
    "system_status_tool",
    "finance_recent_transactions_tool",
    "finance_category_totals_tool",
    "trading_mt5_account_status_tool",
    "trading_bot_signals_tool",
    "trading_coach_query_tool",
    "trading_preflight_check_tool",
    "workspace_calendar_agenda_tool",
    "workspace_unread_emails_tool",
    "workspace_create_email_draft_tool",
    "workspace_schedule_event_tool",
    "workspace_send_email_tool",
    "project_search_knowledge_tool",
    "project_git_status_tool",
    "project_scaffold_tool",
    "project_run_tests_tool",
]
