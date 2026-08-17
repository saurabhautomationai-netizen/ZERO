"""Central Tool Registry for ZERO."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from zero_core.tools.base import BaseTool, ToolResult


class ToolRegistry:
    """Registry managing tool lifecycle, schemas, and execution."""

    def __init__(self, tools: Optional[List[BaseTool]] = None):
        self._tools: Dict[str, BaseTool] = {}
        if tools:
            for t in tools:
                self.register(t)

    def register(self, tool_instance: BaseTool) -> None:
        """Registers a tool instance. Overwrites existing tool if same name."""
        if not tool_instance.name:
            raise ValueError("Cannot register a tool without a valid name")
        self._tools[tool_instance.name] = tool_instance

    def unregister(self, tool_name: str) -> Optional[BaseTool]:
        """Unregisters and returns the removed tool, or None if not found."""
        return self._tools.pop(tool_name, None)

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by name."""
        return self._tools.get(tool_name)

    def has(self, tool_name: str) -> bool:
        """Checks if a tool name is registered."""
        return tool_name in self._tools

    def list_tools(self) -> List[BaseTool]:
        """Returns all registered tool instances."""
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Returns schemas for all registered tools formatted for LLM function calling."""
        return [t.get_schema() for t in self._tools.values()]

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Executes a tool by name with provided arguments."""
        tool_instance = self.get(tool_name)
        if tool_instance is None:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' is not registered in ToolRegistry",
            )
        return tool_instance.execute(**kwargs)
