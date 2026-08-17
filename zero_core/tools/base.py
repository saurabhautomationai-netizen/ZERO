"""Tool definition and execution framework for ZERO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Type
from pydantic import BaseModel, ValidationError


@dataclass
class ToolResult:
    """Represents the standardized result of a tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseTool:
    """Abstract base class for all tools in ZERO."""

    name: str = ""
    description: str = ""
    args_model: Optional[Type[BaseModel]] = None
    risk_level: str = "read_only"  # 'read_only', 'safe_write', 'destructive'

    def __init__(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        args_model: Optional[Type[BaseModel]] = None,
        risk_level: Optional[str] = None,
        func: Optional[Callable[..., Any]] = None,
    ):
        if name:
            self.name = name
        if description:
            self.description = description
        if args_model:
            self.args_model = args_model
        if risk_level:
            self.risk_level = risk_level
        self._func = func

    def get_schema(self) -> Dict[str, Any]:
        """Returns OpenAPI/Function-calling compatible schema."""
        parameters = {}
        if self.args_model is not None:
            parameters = self.args_model.model_json_schema()
        else:
            parameters = {"type": "object", "properties": {}}

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
                "risk_level": self.risk_level,
            },
        }

    def execute(self, **kwargs) -> ToolResult:
        """Validates arguments and executes the tool."""
        # 1. Validate arguments against Pydantic model if provided
        validated_kwargs = kwargs
        if self.args_model is not None:
            try:
                validated_model = self.args_model(**kwargs)
                validated_kwargs = validated_model.model_dump()
            except ValidationError as exc:
                return ToolResult(
                    success=False,
                    error=f"Argument validation error: {exc}",
                    metadata={"raw_args": kwargs},
                )
            except Exception as exc:
                return ToolResult(
                    success=False,
                    error=f"Unexpected validation error: {exc}",
                    metadata={"raw_args": kwargs},
                )

        # 2. Execute implementation
        try:
            if self._func is not None:
                res = self._func(**validated_kwargs)
            else:
                res = self._run(**validated_kwargs)
            return ToolResult(
                success=True,
                output=res,
                metadata={"risk_level": self.risk_level},
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                metadata={"exception_type": type(exc).__name__},
            )

    def _run(self, **kwargs) -> Any:
        """Override in subclasses if not passing a callable func."""
        raise NotImplementedError("Subclasses must implement _run or provide a func callable")


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    args_model: Optional[Type[BaseModel]] = None,
    risk_level: str = "read_only",
) -> Callable[[Callable[..., Any]], BaseTool]:
    """Decorator to convert a Python function into a BaseTool instance."""

    def decorator(fn: Callable[..., Any]) -> BaseTool:
        tool_name = name or fn.__name__
        tool_desc = description or (fn.__doc__ or "").strip()
        return BaseTool(
            name=tool_name,
            description=tool_desc,
            args_model=args_model,
            risk_level=risk_level,
            func=fn,
        )

    return decorator
