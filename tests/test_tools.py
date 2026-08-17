from __future__ import annotations

import tempfile
from pathlib import Path
from pydantic import BaseModel, Field

from zero_core.tools import (
    BaseTool,
    ToolRegistry,
    ToolResult,
    build_default_tool_registry,
    list_dir_tool,
    read_file_tool,
    system_status_tool,
    tool,
)


class SampleCalculatorInput(BaseModel):
    a: int = Field(description="First number")
    b: int = Field(description="Second number")


@tool(
    name="add_numbers",
    description="Adds two integers together",
    args_model=SampleCalculatorInput,
    risk_level="read_only",
)
def add_numbers_tool(a: int, b: int) -> int:
    return a + b


def test_tool_decorator_and_schema():
    schema = add_numbers_tool.get_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "add_numbers"
    assert "parameters" in schema["function"]
    assert "a" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["risk_level"] == "read_only"


def test_tool_execution_success():
    res = add_numbers_tool.execute(a=10, b=25)
    assert res.success is True
    assert res.output == 35
    assert res.error is None
    assert res.metadata["risk_level"] == "read_only"


def test_tool_execution_validation_error():
    # Pass invalid type that fails pydantic validation
    res = add_numbers_tool.execute(a="not_a_number", b=25)
    assert res.success is False
    assert res.output is None
    assert "validation error" in res.error.lower()
    assert "raw_args" in res.metadata


def test_tool_registry_management():
    reg = ToolRegistry()
    assert len(reg.list_tools()) == 0

    reg.register(add_numbers_tool)
    assert reg.has("add_numbers") is True
    assert reg.get("add_numbers") == add_numbers_tool
    assert len(reg.list_tools()) == 1

    schemas = reg.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "add_numbers"

    res = reg.execute("add_numbers", a=5, b=7)
    assert res.success is True
    assert res.output == 12

    unregistered = reg.unregister("add_numbers")
    assert unregistered == add_numbers_tool
    assert reg.has("add_numbers") is False


def test_tool_registry_executes_unregistered_tool():
    reg = ToolRegistry()
    res = reg.execute("non_existent_tool", x=1)
    assert res.success is False
    assert "not registered" in res.error


def test_builtin_read_file_tool(tmp_path: Path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("Hello from ZERO test suite!", encoding="utf-8")

    res = read_file_tool.execute(file_path=str(test_file))
    assert res.success is True
    assert res.output == "Hello from ZERO test suite!"


def test_builtin_read_file_tool_missing():
    res = read_file_tool.execute(file_path="nonexistent/fake_file.txt")
    assert res.success is False
    assert "not found" in res.error.lower()


def test_builtin_list_directory_tool(tmp_path: Path):
    (tmp_path / "subfile.txt").write_text("content", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    res = list_dir_tool.execute(dir_path=str(tmp_path))
    assert res.success is True
    names = [item["name"] for item in res.output]
    assert "subdir" in names
    assert "subfile.txt" in names


def test_builtin_system_status_tool():
    res = system_status_tool.execute()
    assert res.success is True
    assert "os" in res.output
    assert "python_version" in res.output
    assert "zero_root" in res.output


def test_default_tool_registry_factory():
    reg = build_default_tool_registry()
    assert reg.has("read_file")
    assert reg.has("list_directory")
    assert reg.has("system_status")
    assert len(reg.list_tools()) >= 3
