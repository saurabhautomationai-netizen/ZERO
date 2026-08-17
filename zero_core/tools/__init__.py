"""Tools and Tool Registry package for ZERO."""

from zero_core.tools.base import BaseTool, ToolResult, tool
from zero_core.tools.definitions.filesystem import (
    BUILTIN_TOOLS,
    list_dir_tool,
    read_file_tool,
    system_status_tool,
)
from zero_core.tools.registry import ToolRegistry


def build_default_tool_registry() -> ToolRegistry:
    """Factory returning a ToolRegistry pre-populated with standard built-in tools."""
    return ToolRegistry(tools=list(BUILTIN_TOOLS))


__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "tool",
    "build_default_tool_registry",
    "BUILTIN_TOOLS",
    "read_file_tool",
    "list_dir_tool",
    "system_status_tool",
]
