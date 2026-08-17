"""Safe filesystem and system inspection tools for ZERO."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from zero_core import config
from zero_core.tools.base import BaseTool, tool


class ReadFileInput(BaseModel):
    file_path: str = Field(description="Absolute or relative path to the file to read")
    max_bytes: int = Field(default=10000, description="Maximum number of bytes to read (capped at 100KB)")


class ListDirInput(BaseModel):
    dir_path: str = Field(default=".", description="Path to directory to list")


@tool(
    name="read_file",
    description="Safely reads UTF-8 text from a local file up to max_bytes.",
    args_model=ReadFileInput,
    risk_level="read_only",
)
def read_file_tool(file_path: str, max_bytes: int = 10000) -> str:
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise IsADirectoryError(f"Path is a directory, not a file: {file_path}")

    # Enforce safe read cap
    capped_bytes = min(max_bytes, 102400)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(capped_bytes)


@tool(
    name="list_directory",
    description="Lists files and subdirectories within a target directory.",
    args_model=ListDirInput,
    risk_level="read_only",
)
def list_dir_tool(dir_path: str = ".") -> List[Dict[str, Any]]:
    path = Path(dir_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {dir_path}")

    results = []
    for item in sorted(os.listdir(path)):
        full_p = path / item
        results.append({
            "name": item,
            "is_dir": full_p.is_dir(),
            "size_bytes": full_p.stat().st_size if full_p.is_file() else None,
        })
    return results


@tool(
    name="system_status",
    description="Returns host environment, operating system, and project root status.",
    risk_level="read_only",
)
def system_status_tool() -> Dict[str, Any]:
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": platform.python_version(),
        "zero_root": str(config.ZERO_ROOT),
        "agency_path": str(config.AGENCY_AGENTS_PATH),
    }


BUILTIN_TOOLS: List[BaseTool] = [
    read_file_tool,
    list_dir_tool,
    system_status_tool,
]
